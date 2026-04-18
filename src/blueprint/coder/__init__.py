"""Coder backends and bounded job execution."""

from blueprint.coder.claude import (
    ClaudeCodeCoder,
    ClaudeNotFoundError,
    ClaudeRunError,
    ClaudeRunResult,
    build_claude_exec_command,
    run_claude_print,
)
from blueprint.coder.codex import (
    CodexCoder,
    CodexNotFoundError,
    CodexRunError,
    CodexRunResult,
    build_codex_exec_command,
    run_codex_exec,
)
from blueprint.coder.core import (
    CoderBackend,
    CoderExecutionError,
    CoderJobRun,
    CoderRequest,
    CoderResult,
    FileSnapshot,
    build_coder_request,
    render_job_scope,
    run_coder_job,
)
from blueprint.coder.openai import OpenAIResponsesCoder


def create_coder_backend(name: str, *, model: str | None = None) -> CoderBackend:
    if name == "codex":
        return CodexCoder(model=model)
    if name == "claude":
        return ClaudeCodeCoder(model=model)
    if name == "openai":
        return OpenAIResponsesCoder(model=model)
    raise ValueError(f"unknown coder backend: {name}")


__all__ = [
    "ClaudeCodeCoder",
    "ClaudeNotFoundError",
    "ClaudeRunError",
    "ClaudeRunResult",
    "CodexCoder",
    "CodexNotFoundError",
    "CodexRunError",
    "CodexRunResult",
    "CoderBackend",
    "CoderExecutionError",
    "CoderJobRun",
    "CoderRequest",
    "CoderResult",
    "FileSnapshot",
    "OpenAIResponsesCoder",
    "build_claude_exec_command",
    "build_codex_exec_command",
    "build_coder_request",
    "create_coder_backend",
    "render_job_scope",
    "run_claude_print",
    "run_codex_exec",
    "run_coder_job",
]
