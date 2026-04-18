from pathlib import Path
import json
import shutil

import yaml

from blueprint.compiler import compile_ir
from blueprint.planner import job_manifest_path, write_job_manifests
from blueprint.verifier.core import VERIFY_JOB_MANIFEST, VERIFY_STALE_REVISION, verify_job


FIXTURES_ROOT = Path(__file__).parent / "fixtures"


def test_verify_job_passes_for_written_unit_manifest(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    shutil.copytree(FIXTURES_ROOT / "minimal_valid_repo", repo_root)

    compile_ir(repo_root)
    write_job_manifests(repo_root)
    report = verify_job(repo_root, job_manifest_path("unit:payment_service"))

    assert report.ok is True


def test_verify_job_rejects_stale_revision(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    shutil.copytree(FIXTURES_ROOT / "minimal_valid_repo", repo_root)

    compile_ir(repo_root)
    write_job_manifests(repo_root)

    unit_path = repo_root / ".arch/units/payment_service.yaml"
    unit = yaml.safe_load(unit_path.read_text(encoding="utf-8"))
    unit["tests"].append("tests/unit/payments/test_service_v2.py")
    unit_path.write_text(yaml.safe_dump(unit, sort_keys=False), encoding="utf-8")

    report = verify_job(repo_root, job_manifest_path("unit:payment_service"))

    assert report.ok is False
    assert any(item.code == VERIFY_STALE_REVISION for item in report.diagnostics)


def test_verify_job_rejects_tampered_manifest(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    shutil.copytree(FIXTURES_ROOT / "minimal_valid_repo", repo_root)

    compile_ir(repo_root)
    write_job_manifests(repo_root)

    manifest_path = repo_root / job_manifest_path("unit:payment_service")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["owned_files"].append("app/payments/extra.py")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report = verify_job(repo_root, manifest_path)

    assert report.ok is False
    assert any(item.code == VERIFY_JOB_MANIFEST for item in report.diagnostics)


def test_verify_job_is_scoped_to_the_selected_job(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    shutil.copytree(FIXTURES_ROOT / "minimal_valid_repo", repo_root)

    (repo_root / ".arch/units/notification_service.yaml").write_text(
        "\n".join(
            [
                "id: notification_service",
                "kind: service",
                "language: python",
                "generation_mode: managed",
                "layer: service",
                "files:",
                "  - app/notifications/service.py",
                "tests:",
                "  - tests/unit/notifications/test_service.py",
                "",
            ]
        ),
        encoding="utf-8",
    )
    ownership_path = repo_root / ".arch/ownership.yaml"
    ownership = yaml.safe_load(ownership_path.read_text(encoding="utf-8"))
    ownership["unit_files"]["notification_service"] = ["app/notifications/service.py"]
    ownership_path.write_text(yaml.safe_dump(ownership, sort_keys=False), encoding="utf-8")

    compile_ir(repo_root)
    write_job_manifests(repo_root)
    report = verify_job(repo_root, job_manifest_path("unit:payment_service"))

    assert report.ok is True
