from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any

import yaml

from blueprint.compiler import CompileError, compile_ir
from blueprint.ir.validator import validate_ir
from blueprint.revisions import RevisionValidationError, create_revision


CASES_ROOT = Path(__file__).parent / "conformance" / "cases"


def test_conformance_cases() -> None:
    revision_ids: dict[str, str] = {}

    for case_dir in sorted(CASES_ROOT.iterdir()):
        if not case_dir.is_dir():
            continue
        case = load_case(case_dir)
        case_id = case["id"]
        repo_root = case_dir / "repo"
        expected_root = case_dir / "expected"

        validate_expectation = case["expect"]["validate"]
        report = validate_ir(repo_root)
        assert report.ok is validate_expectation["ok"], case_id
        if not validate_expectation["ok"]:
            assert diagnostics_payload(report.diagnostics) == validate_expectation["diagnostics"], case_id

        revision_expectation = case["expect"].get("create_revision")
        if revision_expectation:
            if revision_expectation["ok"]:
                revision = create_revision(repo_root)
                assert revision.revision_id == revision_expectation["revision_id"], case_id
                same_as = revision_expectation.get("same_revision_as")
                if same_as is not None:
                    assert revision.revision_id == revision_ids[same_as], case_id
                expected_snapshot = expected_root / "revision.json"
                if expected_snapshot.exists():
                    assert revision.serialized_snapshot == expected_snapshot.read_text(encoding="utf-8"), case_id
                revision_ids[case_id] = revision.revision_id
            else:
                try:
                    create_revision(repo_root)
                except RevisionValidationError as exc:
                    assert diagnostics_payload(exc.report.diagnostics) == revision_expectation["diagnostics"], case_id
                else:
                    raise AssertionError(f"{case_id}: expected create_revision to fail")

        compile_expectation = case["expect"].get("compile")
        if compile_expectation:
            compile_repo = case_dir / ".tmp-compile"
            if compile_repo.exists():
                shutil.rmtree(compile_repo)
            shutil.copytree(repo_root, compile_repo)
            try:
                if compile_expectation["ok"]:
                    result = compile_ir(compile_repo)
                    assert list(result.emitted_files) == compile_expectation["emitted_files"], case_id
                    compare_tree(
                        compile_repo,
                        expected_root / "emitted",
                        compile_expectation["emitted_files"],
                        case_id,
                    )
                else:
                    try:
                        compile_ir(compile_repo)
                    except CompileError as exc:
                        assert str(exc) == compile_expectation["error"], case_id
                    except RevisionValidationError as exc:
                        assert diagnostics_payload(exc.report.diagnostics) == compile_expectation["diagnostics"], case_id
                    else:
                        raise AssertionError(f"{case_id}: expected compile to fail")
            finally:
                if compile_repo.exists():
                    shutil.rmtree(compile_repo)


def load_case(case_dir: Path) -> dict[str, Any]:
    return yaml.safe_load((case_dir / "case.yaml").read_text(encoding="utf-8"))


def diagnostics_payload(diagnostics: list[Any]) -> list[dict[str, str]]:
    return [
        {
            "code": item.code,
            "path": item.path,
            "message": item.message,
        }
        for item in diagnostics
    ]


def compare_tree(repo_root: Path, expected_root: Path, emitted_files: list[str], case_id: str) -> None:
    for relative_path in emitted_files:
        actual_path = repo_root / relative_path
        expected_path = expected_root / relative_path
        assert actual_path.is_file(), f"{case_id}: missing emitted file {relative_path}"
        assert expected_path.is_file(), f"{case_id}: missing expected file {relative_path}"
        actual = actual_path.read_text(encoding="utf-8")
        expected = expected_path.read_text(encoding="utf-8")
        assert actual == expected, f"{case_id}: emitted content mismatch for {relative_path}"

