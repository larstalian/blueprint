"""Verification for deterministic outputs and managed Python sources."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from blueprint.compiler.core import CompileError, build_compiler_outputs
from blueprint.ir.validator import Diagnostic
from blueprint.revisions import RevisionValidationError, create_revision


VERIFY_COMPILER_OUTPUT = "verify.compiler_output"
VERIFY_MISSING_GENERATED_FILE = "verify.missing_generated_file"
VERIFY_GENERATED_FILE_MISMATCH = "verify.generated_file_mismatch"
VERIFY_MISSING_UNIT_FILE = "verify.missing_unit_file"
VERIFY_PYTHON_SYNTAX = "verify.python_syntax"
VERIFY_STALE_REVISION = "verify.stale_revision"


@dataclass
class VerificationReport:
    revision_id: Optional[str] = None
    diagnostics: List[Diagnostic] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.diagnostics

    def add(self, code: str, path: str, message: str) -> None:
        self.diagnostics.append(Diagnostic(code=code, path=path, message=message))


def verify_repo(
    repo_root: Path,
    *,
    expected_revision_id: str | None = None,
) -> VerificationReport:
    repo_root = Path(repo_root).resolve()
    try:
        revision = create_revision(repo_root)
    except RevisionValidationError as exc:
        return VerificationReport(diagnostics=list(exc.report.diagnostics))

    report = VerificationReport(revision_id=revision.revision_id)
    if expected_revision_id is not None and revision.revision_id != expected_revision_id:
        report.add(
            VERIFY_STALE_REVISION,
            ".arch",
            (
                f"expected revision '{expected_revision_id}' but found "
                f"'{revision.revision_id}'"
            ),
        )

    try:
        expected_outputs = build_compiler_outputs(revision)
    except CompileError as exc:
        report.add(
            VERIFY_COMPILER_OUTPUT,
            ".arch/ownership.yaml#compiler_files",
            str(exc),
        )
        return report

    for relative_path in sorted(revision.snapshot["ownership"]["compiler_files"]):
        expected = expected_outputs.get(relative_path)
        if expected is None:
            report.add(
                VERIFY_COMPILER_OUTPUT,
                relative_path,
                "no deterministic output exists for compiler-owned file",
            )
            continue

        output_path = repo_root / relative_path
        if not output_path.is_file():
            report.add(
                VERIFY_MISSING_GENERATED_FILE,
                relative_path,
                "missing compiler-owned file",
            )
            continue

        actual = output_path.read_text(encoding="utf-8")
        if actual != expected:
            report.add(
                VERIFY_GENERATED_FILE_MISMATCH,
                relative_path,
                "compiler-owned file does not match deterministic output",
            )

    for relative_path in _managed_unit_files(revision.snapshot):
        output_path = repo_root / relative_path
        if not output_path.is_file():
            report.add(
                VERIFY_MISSING_UNIT_FILE,
                relative_path,
                "missing managed unit file",
            )
            continue
        if output_path.suffix != ".py":
            continue
        _verify_python_syntax(report, output_path, relative_path)

    return report


def _managed_unit_files(snapshot: dict[str, object]) -> list[str]:
    units = snapshot["collections"]["units"]
    managed_files: list[str] = []
    for unit in units:
        if unit.get("generation_mode") != "managed":
            continue
        for relative_path in unit.get("files", []):
            if isinstance(relative_path, str) and relative_path:
                managed_files.append(relative_path)
    return sorted(managed_files)


def _verify_python_syntax(
    report: VerificationReport,
    output_path: Path,
    relative_path: str,
) -> None:
    source = output_path.read_text(encoding="utf-8")
    try:
        ast.parse(source, filename=relative_path)
    except SyntaxError as exc:
        location = relative_path
        if exc.lineno is not None:
            location = f"{relative_path}#L{exc.lineno}"
        report.add(
            VERIFY_PYTHON_SYNTAX,
            location,
            exc.msg,
        )
