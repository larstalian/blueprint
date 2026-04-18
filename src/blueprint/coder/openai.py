"""Direct OpenAI model execution for bounded patch generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from blueprint.coder.core import (
    CoderExecutionError,
    CoderRequest,
    CoderResult,
    apply_unified_diff,
    render_job_scope,
)


PATCH_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "patch": {"type": "string"},
    },
    "required": ["summary", "patch"],
    "additionalProperties": False,
}


class OpenAIResponsesCoder:
    name = "openai"

    def __init__(self, *, model: str | None = None) -> None:
        self.model = model

    def run(self, request: CoderRequest) -> CoderResult:
        model = request.model or self.model
        if model is None:
            raise CoderExecutionError("openai coder requires an explicit model")

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise CoderExecutionError("openai package is not installed") from exc

        client = OpenAI()
        response = client.responses.create(
            model=model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are a careful software engineer. "
                        "Return one bounded patch that only touches the owned files."
                    ),
                },
                {
                    "role": "user",
                    "content": _render_patch_prompt(request),
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "blueprint_patch",
                    "schema": PATCH_RESPONSE_SCHEMA,
                    "strict": True,
                }
            },
        )
        raw_output = response.output_text
        try:
            payload = json.loads(raw_output)
        except json.JSONDecodeError as exc:
            raise CoderExecutionError(f"openai emitted invalid JSON: {exc.msg}") from exc
        if not isinstance(payload, dict):
            raise CoderExecutionError("openai emitted a non-object JSON payload")

        summary = payload.get("summary")
        patch = payload.get("patch")
        if not isinstance(summary, str) or not isinstance(patch, str):
            raise CoderExecutionError("openai response is missing a valid summary or patch")

        apply_unified_diff(Path(request.worktree_root), patch)
        return CoderResult(
            backend=self.name,
            final_message=summary,
            raw_output=raw_output,
        )


def _render_patch_prompt(request: CoderRequest) -> str:
    lines = [
        render_job_scope(request).rstrip(),
        "",
        "Return strict JSON with:",
        '- "summary": a short plain-English summary of what you changed',
        '- "patch": a raw unified diff that can be applied with `git apply`',
        'Use an empty string for "patch" if no code change is needed.',
        "",
        "Current owned file snapshots:",
    ]
    for snapshot in request.context_files:
        lines.extend(
            [
                f"FILE {snapshot.path}",
                "```",
                snapshot.content.rstrip(),
                "```",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"
