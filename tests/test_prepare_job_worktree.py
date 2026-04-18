from pathlib import Path
import shutil
import subprocess

from blueprint.compiler import compile_ir
from blueprint.planner import (
    job_manifest_path,
    prepare_job_worktree,
    write_execution_result,
    write_job_manifests,
)
from blueprint.verifier import verify_execution_result


FIXTURES_ROOT = Path(__file__).parent / "fixtures"


def test_prepare_job_worktree_creates_detached_worktree_and_copies_manifest(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    shutil.copytree(FIXTURES_ROOT / "minimal_valid_repo", repo_root)

    compile_ir(repo_root)
    _commit_current_repo_state(repo_root)
    write_job_manifests(repo_root)

    worktree = prepare_job_worktree(
        repo_root,
        job_manifest_path("unit:payment_service"),
    )

    worktree_root = Path(worktree.path)
    manifest_path = Path(worktree.manifest_path)

    assert worktree_root.is_dir()
    assert manifest_path.is_file()
    assert manifest_path.read_text(encoding="utf-8") == (
        repo_root / job_manifest_path("unit:payment_service")
    ).read_text(encoding="utf-8")
    top_level = _run_git_output(worktree_root, "rev-parse", "--show-toplevel").strip()
    assert top_level == str(worktree_root)


def test_prepare_job_worktree_supports_git_diff_based_execution_result(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    shutil.copytree(FIXTURES_ROOT / "minimal_valid_repo", repo_root)

    compile_ir(repo_root)
    _commit_current_repo_state(repo_root)
    write_job_manifests(repo_root)
    worktree = prepare_job_worktree(
        repo_root,
        job_manifest_path("unit:payment_service"),
    )

    worktree_root = Path(worktree.path)
    service_path = worktree_root / "app/payments/service.py"
    service_path.write_text(
        service_path.read_text(encoding="utf-8") + "\n\nclass PaymentServiceV2:\n    pass\n",
        encoding="utf-8",
    )

    artifact = write_execution_result(
        worktree_root,
        Path(worktree.manifest_path),
    )

    assert artifact.changed_files == ("app/payments/service.py",)
    report = verify_execution_result(worktree_root, artifact.path)
    assert report.ok is True


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


def _run_git_output(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout
