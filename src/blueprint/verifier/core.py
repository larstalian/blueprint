"""Verification for deterministic outputs and managed Python sources."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import List, Optional

from blueprint.compiler.core import CompileError, build_compiler_outputs
from blueprint.ir.validator import Diagnostic
from blueprint.planner import build_job_manifest, plan_jobs
from blueprint.revisions import RevisionValidationError, create_revision


VERIFY_COMPILER_OUTPUT = "verify.compiler_output"
VERIFY_MISSING_GENERATED_FILE = "verify.missing_generated_file"
VERIFY_GENERATED_FILE_MISMATCH = "verify.generated_file_mismatch"
VERIFY_MISSING_UNIT_FILE = "verify.missing_unit_file"
VERIFY_PYTHON_SYNTAX = "verify.python_syntax"
VERIFY_STALE_REVISION = "verify.stale_revision"
VERIFY_JOB_MANIFEST = "verify.job_manifest"
VERIFY_CHANGED_FILE_SCOPE = "verify.changed_file_scope"
VERIFY_EXECUTION_RESULT = "verify.execution_result"


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

    _verify_compiler_outputs(
        report=report,
        repo_root=repo_root,
        compiler_files=revision.snapshot["ownership"]["compiler_files"],
        expected_outputs=expected_outputs,
    )
    _verify_owned_files(
        report=report,
        repo_root=repo_root,
        owned_files=_managed_unit_files(revision.snapshot),
    )

    return report


def verify_job(
    repo_root: Path,
    manifest_path: Path,
    *,
    changed_files: list[str] | None = None,
) -> VerificationReport:
    repo_root = Path(repo_root).resolve()
    manifest_path = Path(manifest_path)
    if not manifest_path.is_absolute():
        manifest_path = (repo_root / manifest_path).resolve()

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError as exc:
        report = VerificationReport()
        report.add(
            VERIFY_JOB_MANIFEST,
            _relative_to_repo(repo_root, manifest_path),
            f"could not read job manifest: {exc}",
        )
        return report
    except json.JSONDecodeError as exc:
        report = VerificationReport()
        report.add(
            VERIFY_JOB_MANIFEST,
            _relative_to_repo(repo_root, manifest_path),
            f"invalid JSON: {exc.msg}",
        )
        return report

    job_id = manifest.get("job_id")
    if not isinstance(job_id, str) or not job_id:
        report = VerificationReport()
        report.add(
            VERIFY_JOB_MANIFEST,
            _relative_to_repo(repo_root, manifest_path),
            "job manifest is missing a valid job_id",
        )
        return report

    try:
        revision = create_revision(repo_root)
    except RevisionValidationError as exc:
        return VerificationReport(diagnostics=list(exc.report.diagnostics))

    report = VerificationReport(revision_id=revision.revision_id)
    if manifest.get("revision_id") != revision.revision_id:
        report.add(
            VERIFY_STALE_REVISION,
            ".arch",
            (
                f"expected revision '{manifest.get('revision_id')}' but found "
                f"'{revision.revision_id}'"
            ),
        )
        return report

    try:
        expected_outputs = build_compiler_outputs(revision)
    except CompileError as exc:
        report.add(
            VERIFY_COMPILER_OUTPUT,
            ".arch/ownership.yaml#compiler_files",
            str(exc),
        )
        return report

    plan = plan_jobs(repo_root)
    expected_job = next(
        (job for job in plan.snapshot["jobs"] if job.get("job_id") == job_id),
        None,
    )
    if expected_job is None:
        report.add(
            VERIFY_JOB_MANIFEST,
            _relative_to_repo(repo_root, manifest_path),
            f"unknown planned job '{job_id}'",
        )
        return report

    expected_manifest = build_job_manifest(plan.revision_id, expected_job)
    if manifest != expected_manifest:
        report.add(
            VERIFY_JOB_MANIFEST,
            _relative_to_repo(repo_root, manifest_path),
            "job manifest does not match the current deterministic plan",
        )
        return report

    _verify_changed_files(
        report=report,
        changed_files=changed_files,
        owned_files=_as_string_list(expected_job.get("owned_files")),
    )
    if not report.ok:
        return report

    if expected_job["kind"] == "compile" or "compile:compiler_owned" in _as_string_list(
        expected_job.get("depends_on")
    ):
        _verify_compiler_outputs(
            report=report,
            repo_root=repo_root,
            compiler_files=revision.snapshot["ownership"]["compiler_files"],
            expected_outputs=expected_outputs,
        )

    if expected_job["kind"] == "compile":
        return report

    _verify_owned_files(
        report=report,
        repo_root=repo_root,
        owned_files=_as_string_list(expected_job.get("owned_files")),
    )
    return report


def verify_execution_result(repo_root: Path, result_path: Path) -> VerificationReport:
    repo_root = Path(repo_root).resolve()
    result_path = Path(result_path)
    if not result_path.is_absolute():
        result_path = (repo_root / result_path).resolve()

    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except OSError as exc:
        report = VerificationReport()
        report.add(
            VERIFY_EXECUTION_RESULT,
            _relative_to_repo(repo_root, result_path),
            f"could not read execution result: {exc}",
        )
        return report
    except json.JSONDecodeError as exc:
        report = VerificationReport()
        report.add(
            VERIFY_EXECUTION_RESULT,
            _relative_to_repo(repo_root, result_path),
            f"invalid JSON: {exc.msg}",
        )
        return report

    manifest = result.get("job_manifest")
    if not isinstance(manifest, str) or not manifest:
        report = VerificationReport()
        report.add(
            VERIFY_EXECUTION_RESULT,
            _relative_to_repo(repo_root, result_path),
            "execution result is missing a valid job_manifest",
        )
        return report

    changed_files = result.get("changed_files")
    if not isinstance(changed_files, list) or any(
        not isinstance(item, str) or not item for item in changed_files
    ):
        report = VerificationReport()
        report.add(
            VERIFY_EXECUTION_RESULT,
            _relative_to_repo(repo_root, result_path),
            "execution result is missing a valid changed_files list",
        )
        return report

    return verify_job(
        repo_root,
        Path(manifest),
        changed_files=sorted(set(changed_files)),
    )


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


def _verify_compiler_outputs(
    report: VerificationReport,
    repo_root: Path,
    compiler_files: list[str],
    expected_outputs: dict[str, str],
) -> None:
    for relative_path in sorted(compiler_files):
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


def _verify_owned_files(
    report: VerificationReport,
    repo_root: Path,
    owned_files: list[str],
) -> None:
    for relative_path in sorted(owned_files):
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


def _verify_changed_files(
    report: VerificationReport,
    changed_files: list[str] | None,
    owned_files: list[str],
) -> None:
    if changed_files is None:
        return

    allowed_files = set(owned_files)
    for relative_path in sorted(set(changed_files)):
        if relative_path not in allowed_files:
            report.add(
                VERIFY_CHANGED_FILE_SCOPE,
                relative_path,
                "changed file is outside the job ownership boundary",
            )


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


def _as_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _relative_to_repo(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()
