from pathlib import Path
import shutil
import subprocess

from blueprint.coder import CoderResult, run_coder_job
from blueprint.compiler import compile_ir
from blueprint.planner import job_manifest_path, write_job_manifests


FIXTURES_ROOT = Path(__file__).parent / "fixtures"


class TouchOwnedFileCoder:
    name = "fake"

    def run(self, request) -> CoderResult:
        service_path = Path(request.worktree_root) / request.owned_files[0]
        service_path.write_text(
            service_path.read_text(encoding="utf-8") + "\n\nclass OwnedChange:\n    pass\n",
            encoding="utf-8",
        )
        return CoderResult(
            backend=self.name,
            final_message="updated owned file",
            raw_output="ok",
        )


class EscapeScopeCoder:
    name = "fake"

    def run(self, request) -> CoderResult:
        outside_path = Path(request.worktree_root) / "app/payments/contracts.py"
        outside_path.write_text(
            outside_path.read_text(encoding="utf-8") + "\n\nBROKEN = True\n",
            encoding="utf-8",
        )
        return CoderResult(
            backend=self.name,
            final_message="escaped scope",
            raw_output="ok",
        )


def test_run_coder_job_prepares_worktree_writes_result_and_verifies(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    shutil.copytree(FIXTURES_ROOT / "minimal_valid_repo", repo_root)

    compile_ir(repo_root)
    _commit_current_repo_state(repo_root)
    write_job_manifests(repo_root)

    run = run_coder_job(
        repo_root,
        job_manifest_path("unit:payment_service"),
        "Add a marker class.",
        TouchOwnedFileCoder(),
    )

    assert Path(run.worktree.path).is_dir()
    assert run.execution_result.changed_files == ("app/payments/service.py",)
    assert run.ok is True
    assert run.coder_result.final_message == "updated owned file"


def test_run_coder_job_reports_scope_escape(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    shutil.copytree(FIXTURES_ROOT / "minimal_valid_repo", repo_root)

    compile_ir(repo_root)
    _commit_current_repo_state(repo_root)
    write_job_manifests(repo_root)

    run = run_coder_job(
        repo_root,
        job_manifest_path("unit:payment_service"),
        "Break the ownership boundary.",
        EscapeScopeCoder(),
    )

    assert run.ok is False
    assert [diagnostic.code for diagnostic in run.verification.diagnostics] == [
        "verify.changed_file_scope"
    ]


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
