"""Claude Code CLI execution helper."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import subprocess

from blueprint.coder.core import CoderRequest, CoderResult, render_job_scope


@dataclass(frozen=True)
class ClaudeRunResult:
    command: tuple[str, ...]
    cwd: str
    prompt: str
    returncode: int
    payload: dict[str, object]
    final_message: str
    stdout: str
    stderr: str


class ClaudeNotFoundError(RuntimeError):
    """Raised when the local `claude` binary cannot be found."""


class ClaudeRunError(RuntimeError):
    """Raised when `claude -p` fails or emits invalid JSON."""

    def __init__(
        self,
        message: str,
        *,
        command: tuple[str, ...],
        returncode: int | None = None,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        super().__init__(message)
        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class ClaudeCodeCoder:
    name = "claude"

    def __init__(self, *, model: str | None = None) -> None:
        self.model = model

    def run(self, request: CoderRequest) -> CoderResult:
        run = run_claude_print(
            Path(request.worktree_root),
            render_job_scope(request),
            model=request.model or self.model,
        )
        return CoderResult(
            backend=self.name,
            final_message=run.final_message,
            raw_output=run.stdout,
        )


def build_claude_exec_command(
    claude_bin: str,
    cwd: Path,
    *,
    model: str | None = None,
) -> tuple[str, ...]:
    command = [
        claude_bin,
        "-p",
        "--output-format",
        "json",
        "--dangerously-skip-permissions",
        "--cwd",
        str(Path(cwd).resolve()),
    ]
    if model is not None:
        command.extend(["--model", model])
    return tuple(command)


def run_claude_print(
    cwd: Path,
    prompt: str,
    *,
    model: str | None = None,
) -> ClaudeRunResult:
    claude_bin = _resolve_claude_bin()
    command = build_claude_exec_command(claude_bin, cwd, model=model)

    try:
        result = subprocess.run(
            command,
            cwd=str(Path(cwd).resolve()),
            input=prompt,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise ClaudeNotFoundError("claude executable not found on PATH") from exc

    payload = _parse_claude_json(result.stdout, command=command, stderr=result.stderr)
    final_message = _extract_claude_message(payload)
    if result.returncode != 0:
        raise ClaudeRunError(
            f"claude print mode failed with exit code {result.returncode}",
            command=command,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    return ClaudeRunResult(
        command=command,
        cwd=str(Path(cwd).resolve()),
        prompt=prompt,
        returncode=result.returncode,
        payload=payload,
        final_message=final_message,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def _resolve_claude_bin() -> str:
    claude_bin = shutil.which("claude")
    if claude_bin is None:
        raise ClaudeNotFoundError("claude executable not found on PATH")
    return claude_bin


def _parse_claude_json(
    stdout: str,
    *,
    command: tuple[str, ...],
    stderr: str,
) -> dict[str, object]:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ClaudeRunError(
            f"claude emitted invalid JSON: {exc.msg}",
            command=command,
            stdout=stdout,
            stderr=stderr,
        ) from exc
    if not isinstance(payload, dict):
        raise ClaudeRunError(
            "claude emitted a non-object JSON payload",
            command=command,
            stdout=stdout,
            stderr=stderr,
        )
    return payload


def _extract_claude_message(payload: dict[str, object]) -> str:
    for key in ("result", "output", "message"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return json.dumps(payload, indent=2, sort_keys=True)
