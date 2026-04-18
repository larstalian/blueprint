from pathlib import Path
import json
import shutil
import subprocess

from blueprint.compiler import compile_ir
from blueprint.planner import job_manifest_path, write_execution_result, write_job_manifests
from blueprint.verifier.core import (
    VERIFY_CHANGED_FILE_SCOPE,
    VERIFY_EXECUTION_RESULT,
    verify_execution_result,
)


FIXTURES_ROOT = Path(__file__).parent / "fixtures"


def test_verify_execution_result_passes_for_valid_unit_result(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    shutil.copytree(FIXTURES_ROOT / "minimal_valid_repo", repo_root)

    compile_ir(repo_root)
    write_job_manifests(repo_root)
    artifact = write_execution_result(
        repo_root,
        job_manifest_path("unit:payment_service"),
        changed_files=["app/payments/service.py", "app/payments/service.py"],
    )

    assert artifact.path == ".arch/manifests/results/unit/payment_service.json"
    assert artifact.changed_files == ("app/payments/service.py",)
    report = verify_execution_result(repo_root, artifact.path)

    assert report.ok is True


def test_verify_execution_result_rejects_scope_violation(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    shutil.copytree(FIXTURES_ROOT / "minimal_valid_repo", repo_root)

    compile_ir(repo_root)
    write_job_manifests(repo_root)
    artifact = write_execution_result(
        repo_root,
        job_manifest_path("unit:payment_service"),
        changed_files=["app/payments/gateway.py"],
    )

    report = verify_execution_result(repo_root, artifact.path)

    assert report.ok is False
    assert any(item.code == VERIFY_CHANGED_FILE_SCOPE for item in report.diagnostics)


def test_verify_execution_result_rejects_invalid_artifact(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    shutil.copytree(FIXTURES_ROOT / "minimal_valid_repo", repo_root)

    result_path = repo_root / ".arch/manifests/results/invalid.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps({"changed_files": ["app/payments/service.py"]}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    report = verify_execution_result(repo_root, result_path)

    assert report.ok is False
    assert any(item.code == VERIFY_EXECUTION_RESULT for item in report.diagnostics)


def test_write_execution_result_can_derive_changed_files_from_git_diff(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    shutil.copytree(FIXTURES_ROOT / "minimal_valid_repo", repo_root)

    compile_ir(repo_root)
    write_job_manifests(repo_root)
    _commit_current_repo_state(repo_root)

    service_path = repo_root / "app/payments/service.py"
    service_path.write_text(
        service_path.read_text(encoding="utf-8") + "\n\nclass PaymentServiceV2:\n    pass\n",
        encoding="utf-8",
    )

    artifact = write_execution_result(
        repo_root,
        job_manifest_path("unit:payment_service"),
    )

    assert artifact.changed_files == ("app/payments/service.py",)
    report = verify_execution_result(repo_root, artifact.path)
    assert report.ok is True


def test_write_execution_result_derives_untracked_scope_violation(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    shutil.copytree(FIXTURES_ROOT / "minimal_valid_repo", repo_root)

    compile_ir(repo_root)
    write_job_manifests(repo_root)
    _commit_current_repo_state(repo_root)

    extra_path = repo_root / "app/payments/extra.py"
    extra_path.parent.mkdir(parents=True, exist_ok=True)
    extra_path.write_text("EXTRA = True\n", encoding="utf-8")

    artifact = write_execution_result(
        repo_root,
        job_manifest_path("unit:payment_service"),
    )

    assert artifact.changed_files == ("app/payments/extra.py",)
    report = verify_execution_result(repo_root, artifact.path)
    assert report.ok is False
    assert any(item.code == VERIFY_CHANGED_FILE_SCOPE for item in report.diagnostics)


def _commit_current_repo_state(repo_root: Path) -> None:
    _run_git(repo_root, "init")
    _run_git(repo_root, "config", "user.name", "Blueprint Tests")
    _run_git(repo_root, "config", "user.email", "blueprint@example.com")
    _run_git(repo_root, "add", ".")
    _run_git(repo_root, "commit", "-m", "baseline")


def _run_git(repo_root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
