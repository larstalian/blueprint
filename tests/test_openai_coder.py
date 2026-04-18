from pathlib import Path
import json
import subprocess
import sys
import types

import pytest

from blueprint.coder import CoderRequest, FileSnapshot, OpenAIResponsesCoder


def test_openai_responses_coder_applies_patch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service_path = tmp_path / "app/payments/service.py"
    service_path.parent.mkdir(parents=True, exist_ok=True)
    service_path.write_text("class PaymentService:\n    pass\n", encoding="utf-8")
    _run_git(tmp_path, "init")

    captured: dict[str, object] = {}

    class FakeResponses:
        def create(self, **kwargs: object) -> object:
            captured.update(kwargs)
            patch = (
                "diff --git a/app/payments/service.py b/app/payments/service.py\n"
                "--- a/app/payments/service.py\n"
                "+++ b/app/payments/service.py\n"
                "@@ -1,2 +1,5 @@\n"
                " class PaymentService:\n"
                "     pass\n"
                "+\n"
                "+class PaymentServiceV2:\n"
                "+    pass\n"
            )
            return types.SimpleNamespace(
                output_text=json.dumps(
                    {"summary": "updated service", "patch": patch},
                )
            )

    class FakeOpenAI:
        def __init__(self) -> None:
            self.responses = FakeResponses()

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeOpenAI))

    request = CoderRequest(
        job_id="unit:payment_service",
        manifest_path=".arch/manifests/jobs/unit/payment_service.json",
        worktree_root=str(tmp_path),
        instructions="Add a second implementation marker.",
        owned_files=("app/payments/service.py",),
        job_manifest='{"job_id":"unit:payment_service"}\n',
        context_files=(
            FileSnapshot(
                path="app/payments/service.py",
                content=service_path.read_text(encoding="utf-8"),
            ),
        ),
        model="gpt-4o-2024-08-06",
    )

    result = OpenAIResponsesCoder().run(request)

    assert captured["model"] == "gpt-4o-2024-08-06"
    assert result.final_message == "updated service"
    assert "PaymentServiceV2" in service_path.read_text(encoding="utf-8")


def test_openai_responses_coder_requires_model(tmp_path: Path) -> None:
    request = CoderRequest(
        job_id="unit:payment_service",
        manifest_path=".arch/manifests/jobs/unit/payment_service.json",
        worktree_root=str(tmp_path),
        instructions="Do the work.",
        owned_files=("app/payments/service.py",),
        job_manifest='{"job_id":"unit:payment_service"}\n',
        context_files=(),
        model=None,
    )

    with pytest.raises(RuntimeError, match="explicit model"):
        OpenAIResponsesCoder().run(request)


def _run_git(repo_root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
