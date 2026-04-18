from pathlib import Path
import subprocess

import pytest

from blueprint.coder.claude import (
    ClaudeNotFoundError,
    ClaudeRunError,
    build_claude_exec_command,
    run_claude_print,
)


def test_build_claude_exec_command_uses_headless_contract(tmp_path: Path) -> None:
    command = build_claude_exec_command(
        "/opt/homebrew/bin/claude",
        tmp_path,
        model="claude-sonnet-4-20250514",
    )

    assert command == (
        "/opt/homebrew/bin/claude",
        "-p",
        "--output-format",
        "json",
        "--dangerously-skip-permissions",
        "--cwd",
        str(tmp_path.resolve()),
        "--model",
        "claude-sonnet-4-20250514",
    )


def test_run_claude_print_parses_json_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_which(name: str) -> str | None:
        assert name == "claude"
        return "/opt/homebrew/bin/claude"

    def fake_run(
        command: tuple[str, ...],
        *,
        cwd: str,
        input: str,
        capture_output: bool,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert cwd == str(tmp_path.resolve())
        assert input == "Make the change."
        assert capture_output is True
        assert text is True
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='{"result":"done","turns":2}\n',
            stderr="",
        )

    monkeypatch.setattr("blueprint.coder.claude.shutil.which", fake_which)
    monkeypatch.setattr("blueprint.coder.claude.subprocess.run", fake_run)

    result = run_claude_print(tmp_path, "Make the change.")

    assert result.returncode == 0
    assert result.final_message == "done"
    assert result.payload == {"result": "done", "turns": 2}


def test_run_claude_print_fails_when_claude_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("blueprint.coder.claude.shutil.which", lambda name: None)

    with pytest.raises(ClaudeNotFoundError, match="claude executable not found"):
        run_claude_print(tmp_path, "Make the change.")


def test_run_claude_print_raises_on_invalid_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("blueprint.coder.claude.shutil.which", lambda name: "/opt/homebrew/bin/claude")

    def fake_run(
        command: tuple[str, ...],
        *,
        cwd: str,
        input: str,
        capture_output: bool,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="not-json\n",
            stderr="",
        )

    monkeypatch.setattr("blueprint.coder.claude.subprocess.run", fake_run)

    with pytest.raises(ClaudeRunError, match="invalid JSON"):
        run_claude_print(tmp_path, "Make the change.")
