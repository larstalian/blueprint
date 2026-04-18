"""Codex CLI execution helper."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any

from blueprint.coder.core import CoderRequest, CoderResult, render_job_scope


@dataclass(frozen=True)
class CodexRunResult:
    command: tuple[str, ...]
    cwd: str
    prompt: str
    returncode: int
    events: tuple[dict[str, Any], ...]
    final_message: str | None
    stdout: str
    stderr: str


class CodexNotFoundError(RuntimeError):
    """Raised when the local `codex` binary cannot be found."""


class CodexRunError(RuntimeError):
    """Raised when `codex exec` fails or emits invalid JSONL."""

    def __init__(
        self,
        message: str,
        *,
        command: tuple[str, ...],
        returncode: int | None = None,
        stdout: str = "",
        stderr: str = "",
        events: tuple[dict[str, Any], ...] = (),
        final_message: str | None = None,
    ) -> None:
        super().__init__(message)
        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.events = events
        self.final_message = final_message


class CodexCoder:
    name = "codex"

    def __init__(self, *, model: str | None = None) -> None:
        self.model = model

    def run(self, request: CoderRequest) -> CoderResult:
        run = run_codex_exec(
            Path(request.worktree_root),
            render_job_scope(request),
            model=request.model or self.model,
        )
        return CoderResult(
            backend=self.name,
            final_message=run.final_message or "",
            raw_output=run.stdout,
        )


def build_codex_exec_command(
    codex_bin: str,
    cwd: Path,
    *,
    model: str | None = None,
    output_last_message_path: Path,
) -> tuple[str, ...]:
    command = [codex_bin, "exec"]
    if model is not None:
        command.extend(["-m", model])
    command.extend(
        [
            "--json",
            "--output-last-message",
            str(output_last_message_path),
            "--color",
            "never",
            "--ephemeral",
            "--full-auto",
            "--cd",
            str(Path(cwd).resolve()),
            "-",
        ]
    )
    return tuple(command)


def run_codex_exec(
    cwd: Path,
    prompt: str,
    *,
    model: str | None = None,
) -> CodexRunResult:
    codex_bin = _resolve_codex_bin()
    output_fd, output_path = tempfile.mkstemp(prefix="blueprint-codex-", suffix=".txt")
    os.close(output_fd)
    output_file = Path(output_path)
    command = build_codex_exec_command(
        codex_bin,
        cwd,
        model=model,
        output_last_message_path=output_file,
    )

    try:
        result = subprocess.run(
            command,
            cwd=str(Path(cwd).resolve()),
            input=prompt,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise CodexNotFoundError("codex executable not found on PATH") from exc

    try:
        events = _parse_jsonl(result.stdout, command=command, stderr=result.stderr)
        final_message = (
            output_file.read_text(encoding="utf-8") if output_file.exists() else None
        )
        if result.returncode != 0:
            raise CodexRunError(
                f"codex exec failed with exit code {result.returncode}",
                command=command,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                events=events,
                final_message=final_message,
            )
        return CodexRunResult(
            command=command,
            cwd=str(Path(cwd).resolve()),
            prompt=prompt,
            returncode=result.returncode,
            events=events,
            final_message=final_message,
            stdout=result.stdout,
            stderr=result.stderr,
        )
    finally:
        output_file.unlink(missing_ok=True)


def _resolve_codex_bin() -> str:
    codex_bin = shutil.which("codex")
    if codex_bin is None:
        raise CodexNotFoundError("codex executable not found on PATH")
    return codex_bin


def _parse_jsonl(
    stdout: str,
    *,
    command: tuple[str, ...],
    stderr: str,
) -> tuple[dict[str, Any], ...]:
    events: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CodexRunError(
                f"codex emitted invalid JSONL: {exc.msg}",
                command=command,
                stdout=stdout,
                stderr=stderr,
            ) from exc
        if not isinstance(event, dict):
            raise CodexRunError(
                "codex emitted a non-object JSON event",
                command=command,
                stdout=stdout,
                stderr=stderr,
            )
        events.append(event)
    return tuple(events)
