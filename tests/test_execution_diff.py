from pathlib import Path
import json
import shutil
import subprocess

from blueprint.compiler import compile_ir
from blueprint.planner import (
    build_execution_diff,
    job_manifest_path,
    prepare_job_worktree,
    write_execution_result,
    write_job_manifests,
)


FIXTURES_ROOT = Path(__file__).parent / "fixtures"


def test_build_execution_diff_returns_changed_files_and_patch(tmp_path: Path) -> None:
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
    artifact = write_execution_result(worktree_root, Path(worktree.manifest_path))

    execution_diff = build_execution_diff(worktree_root, artifact.path)

    assert execution_diff.base_ref == "HEAD"
    assert execution_diff.changed_files == ("app/payments/service.py",)
    assert "diff --git a/app/payments/service.py b/app/payments/service.py" in execution_diff.diff
    assert "+class PaymentServiceV2:" in execution_diff.diff


def test_build_execution_diff_rejects_invalid_artifact(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    shutil.copytree(FIXTURES_ROOT / "minimal_valid_repo", repo_root)

    result_path = repo_root / ".arch/manifests/results/invalid.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps({"job_manifest": ".arch/manifests/jobs/unit/payment_service.json"}, indent=2) + "\n",
        encoding="utf-8",
    )

    try:
        build_execution_diff(repo_root, result_path)
    except ValueError as exc:
        assert "changed_files" in str(exc)
    else:
        raise AssertionError("expected build_execution_diff to reject invalid artifact")


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
