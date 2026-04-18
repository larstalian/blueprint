from pathlib import Path
import subprocess

import pytest

from blueprint.coder.codex import (
    CodexNotFoundError,
    CodexRunError,
    build_codex_exec_command,
    run_codex_exec,
)


def test_build_codex_exec_command_uses_noninteractive_exec_contract(tmp_path: Path) -> None:
    command = build_codex_exec_command(
        "/opt/homebrew/bin/codex",
        tmp_path,
        model="gpt-5",
        output_last_message_path=tmp_path / "last-message.txt",
    )

    assert command == (
        "/opt/homebrew/bin/codex",
        "exec",
        "-m",
        "gpt-5",
        "--json",
        "--output-last-message",
        str(tmp_path / "last-message.txt"),
        "--color",
        "never",
        "--ephemeral",
        "--full-auto",
        "--cd",
        str(tmp_path.resolve()),
        "-",
    )


def test_run_codex_exec_parses_jsonl_and_last_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    calls: dict[str, object] = {}

    def fake_which(name: str) -> str | None:
        assert name == "codex"
        return "/opt/homebrew/bin/codex"

    def fake_run(
        command: list[str],
        *,
        cwd: str,
        input: str,
        capture_output: bool,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        calls["command"] = tuple(command)
        calls["cwd"] = cwd
        calls["input"] = input
        calls["capture_output"] = capture_output
        calls["text"] = text
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text("done", encoding="utf-8")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='{"type":"event","step":"done"}\n',
            stderr="",
        )

    monkeypatch.setattr("blueprint.coder.codex.shutil.which", fake_which)
    monkeypatch.setattr("blueprint.coder.codex.subprocess.run", fake_run)

    result = run_codex_exec(worktree, "Make the change.", model="gpt-5")

    assert calls["command"] == result.command
    assert calls["cwd"] == str(worktree.resolve())
    assert calls["input"] == "Make the change."
    assert calls["capture_output"] is True
    assert calls["text"] is True
    assert result.cwd == str(worktree.resolve())
    assert result.returncode == 0
    assert result.final_message == "done"
    assert result.events == ({"type": "event", "step": "done"},)


def test_run_codex_exec_fails_when_codex_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("blueprint.coder.codex.shutil.which", lambda name: None)

    with pytest.raises(CodexNotFoundError, match="codex executable not found"):
        run_codex_exec(tmp_path, "Make the change.")


def test_run_codex_exec_raises_on_nonzero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    monkeypatch.setattr("blueprint.coder.codex.shutil.which", lambda name: "/opt/homebrew/bin/codex")

    def fake_run(
        command: list[str],
        *,
        cwd: str,
        input: str,
        capture_output: bool,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text("partial", encoding="utf-8")
        return subprocess.CompletedProcess(
            command,
            2,
            stdout='{"type":"event","step":"failed"}\n',
            stderr="boom",
        )

    monkeypatch.setattr("blueprint.coder.codex.subprocess.run", fake_run)

    with pytest.raises(CodexRunError) as exc_info:
        run_codex_exec(worktree, "Make the change.")

    assert exc_info.value.returncode == 2
    assert exc_info.value.final_message == "partial"
    assert exc_info.value.stderr == "boom"
