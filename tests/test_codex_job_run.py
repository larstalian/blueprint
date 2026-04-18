from pathlib import Path
import shutil
import stat
import subprocess

import pytest

from blueprint.coder import CodexCoder, run_coder_job
from blueprint.compiler import compile_ir
from blueprint.planner import job_manifest_path, write_job_manifests


FIXTURES_ROOT = Path(__file__).parent / "fixtures"


def test_run_coder_job_with_codex_creates_verified_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = tmp_path / "repo"
    shutil.copytree(FIXTURES_ROOT / "minimal_valid_repo", repo_root)

    compile_ir(repo_root)
    _commit_current_repo_state(repo_root)
    write_job_manifests(repo_root)

    fake_codex = _write_fake_codex(tmp_path / "fake-codex")
    monkeypatch.setattr("blueprint.coder.codex.shutil.which", lambda name: str(fake_codex))

    run = run_coder_job(
        repo_root,
        job_manifest_path("unit:payment_service"),
        "Add a minimal implementation marker.",
        CodexCoder(model="gpt-5"),
        model="gpt-5",
    )

    assert run.ok is True
    assert Path(run.worktree.path).is_dir()
    assert run.coder_result.backend == "codex"
    assert run.coder_result.final_message == "done"
    assert run.execution_result.changed_files == ("app/payments/service.py",)
    assert "CodexTouched" in (Path(run.worktree.path) / "app/payments/service.py").read_text(
        encoding="utf-8"
    )


def _write_fake_codex(path: Path) -> Path:
    path.write_text(
        """#!/usr/bin/env python3
from pathlib import Path
import json
import sys

args = sys.argv[1:]
cwd = None
message_path = None
i = 0
while i < len(args):
    arg = args[i]
    if arg in {"-m", "--model", "--output-last-message", "--color", "--cd"}:
        if arg == "--cd":
            cwd = args[i + 1]
        if arg == "--output-last-message":
            message_path = args[i + 1]
        i += 2
        continue
    i += 1

if cwd is None or message_path is None:
    raise SystemExit(2)

worktree_root = Path(cwd)
service_path = worktree_root / "app/payments/service.py"
service_path.write_text(
    service_path.read_text(encoding="utf-8") + "\\n\\nclass CodexTouched:\\n    pass\\n",
    encoding="utf-8",
)
Path(message_path).write_text("done", encoding="utf-8")
print(json.dumps({"type": "event", "step": "done"}))
""",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


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
