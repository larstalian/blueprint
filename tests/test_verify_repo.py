from pathlib import Path
import shutil

from blueprint.compiler import compile_ir
from blueprint.verifier.core import (
    VERIFY_GENERATED_FILE_MISMATCH,
    VERIFY_MISSING_GENERATED_FILE,
    VERIFY_MISSING_UNIT_FILE,
    VERIFY_PYTHON_SYNTAX,
    VERIFY_STALE_REVISION,
    verify_repo,
)


FIXTURES_ROOT = Path(__file__).parent / "fixtures"


def test_verify_repo_passes_after_compile(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    shutil.copytree(FIXTURES_ROOT / "minimal_valid_repo", repo_root)

    compile_ir(repo_root)
    report = verify_repo(repo_root)

    assert report.ok is True
    assert report.revision_id is not None


def test_verify_repo_reports_missing_compiler_output(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    shutil.copytree(FIXTURES_ROOT / "minimal_valid_repo", repo_root)

    report = verify_repo(repo_root)

    assert report.ok is False
    assert any(item.code == VERIFY_MISSING_GENERATED_FILE for item in report.diagnostics)


def test_verify_repo_reports_drifted_compiler_output(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    shutil.copytree(FIXTURES_ROOT / "minimal_valid_repo", repo_root)

    compile_ir(repo_root)
    (repo_root / "app/payments/contracts.py").write_text(
        '"""drifted"""' + "\n",
        encoding="utf-8",
    )

    report = verify_repo(repo_root)

    assert report.ok is False
    assert any(item.code == VERIFY_GENERATED_FILE_MISMATCH for item in report.diagnostics)


def test_verify_repo_reports_missing_managed_unit_file(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    shutil.copytree(FIXTURES_ROOT / "minimal_valid_repo", repo_root)

    compile_ir(repo_root)
    (repo_root / "app/payments/service.py").unlink()

    report = verify_repo(repo_root)

    assert report.ok is False
    assert any(item.code == VERIFY_MISSING_UNIT_FILE for item in report.diagnostics)


def test_verify_repo_reports_python_syntax_errors(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    shutil.copytree(FIXTURES_ROOT / "minimal_valid_repo", repo_root)

    compile_ir(repo_root)
    (repo_root / "app/payments/service.py").write_text("def broken(:\n", encoding="utf-8")

    report = verify_repo(repo_root)

    assert report.ok is False
    assert any(item.code == VERIFY_PYTHON_SYNTAX for item in report.diagnostics)


def test_verify_repo_reports_stale_revision(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    shutil.copytree(FIXTURES_ROOT / "minimal_valid_repo", repo_root)

    compile_ir(repo_root)
    report = verify_repo(repo_root, expected_revision_id="stale")

    assert report.ok is False
    assert any(item.code == VERIFY_STALE_REVISION for item in report.diagnostics)
