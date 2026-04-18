"""Shared coder interfaces and job orchestration."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping, Protocol

from blueprint.planner import JobWorktree, ExecutionResultArtifact, prepare_job_worktree, write_execution_result
from blueprint.verifier import VerificationReport, verify_execution_result


@dataclass(frozen=True)
class FileSnapshot:
    path: str
    content: str


@dataclass(frozen=True)
class CoderRequest:
    job_id: str
    manifest_path: str
    worktree_root: str
    instructions: str
    owned_files: tuple[str, ...]
    job_manifest: str
    context_files: tuple[FileSnapshot, ...]
    model: str | None = None


@dataclass(frozen=True)
class CoderResult:
    backend: str
    final_message: str
    raw_output: str


@dataclass(frozen=True)
class CoderJobRun:
    worktree: JobWorktree
    coder_result: CoderResult
    execution_result: ExecutionResultArtifact
    verification: VerificationReport

    @property
    def ok(self) -> bool:
        return self.verification.ok


class CoderExecutionError(RuntimeError):
    """Raised when a coder backend cannot complete a job run."""


class CoderBackend(Protocol):
    name: str

    def run(self, request: CoderRequest) -> CoderResult:
        """Execute one bounded coder request."""


def build_coder_request(
    repo_root: Path,
    manifest_path: Path,
    instructions: str,
    *,
    model: str | None = None,
) -> CoderRequest:
    repo_root = Path(repo_root).resolve()
    manifest_path = _resolve_path(repo_root, manifest_path)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    job_id = manifest.get("job_id")
    if not isinstance(job_id, str) or not job_id:
        raise ValueError("job manifest is missing a valid job_id")

    owned_files = tuple(sorted(_as_string_list(manifest.get("owned_files"))))
    if not owned_files:
        raise ValueError(f"job '{job_id}' does not own any files")

    snapshots = tuple(
        FileSnapshot(
            path=path,
            content=_read_optional_text(repo_root / path),
        )
        for path in owned_files
    )
    return CoderRequest(
        job_id=job_id,
        manifest_path=manifest_path.relative_to(repo_root).as_posix(),
        worktree_root=str(repo_root),
        instructions=instructions,
        owned_files=owned_files,
        job_manifest=json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        context_files=snapshots,
        model=model,
    )


def render_job_scope(request: CoderRequest) -> str:
    lines = [
        "You are executing one bounded coding job inside a detached git worktree.",
        f"Job ID: {request.job_id}",
        f"Worktree root: {request.worktree_root}",
        "Only modify these files:",
    ]
    lines.extend(f"- {path}" for path in request.owned_files)
    lines.extend(
        [
            "Do not edit .arch/manifests or any file outside the owned set.",
            "If the task requires edits outside the owned set, stop and explain that clearly.",
            "",
            "Job manifest:",
            request.job_manifest.rstrip(),
            "",
            "User instructions:",
            request.instructions,
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def run_coder_job(
    repo_root: Path,
    manifest_path: Path,
    instructions: str,
    backend: CoderBackend,
    *,
    model: str | None = None,
    base_ref: str = "HEAD",
) -> CoderJobRun:
    repo_root = Path(repo_root).resolve()
    worktree = prepare_job_worktree(repo_root, manifest_path, base_ref=base_ref)
    worktree_root = Path(worktree.path)
    request = build_coder_request(
        worktree_root,
        Path(worktree.manifest_path),
        instructions,
        model=model,
    )
    coder_result = backend.run(request)
    execution_result = write_execution_result(
        worktree_root,
        Path(worktree.manifest_path),
        base_ref=base_ref,
    )
    verification = verify_execution_result(worktree_root, Path(execution_result.path))
    return CoderJobRun(
        worktree=worktree,
        coder_result=coder_result,
        execution_result=execution_result,
        verification=verification,
    )


def apply_unified_diff(repo_root: Path, patch: str) -> None:
    repo_root = Path(repo_root).resolve()
    if not patch.strip():
        return

    try:
        subprocess.run(
            ["git", "apply", "--whitespace=nowarn", "-"],
            cwd=repo_root,
            input=patch,
            capture_output=True,
            check=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or exc.stdout.strip() or "git apply failed"
        raise CoderExecutionError(message) from exc


def _resolve_path(repo_root: Path, path: Path) -> Path:
    path = Path(path)
    if path.is_absolute():
        return path
    return (repo_root / path).resolve()


def _read_optional_text(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]
