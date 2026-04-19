from pathlib import Path
import shutil

import yaml

from blueprint.planner import write_job_manifests


FIXTURES_ROOT = Path(__file__).parent / "fixtures"


def test_write_job_manifests_writes_expected_files(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    shutil.copytree(FIXTURES_ROOT / "minimal_valid_repo", repo_root)

    stale_path = repo_root / ".arch/manifests/jobs/unit/stale.json"
    stale_path.parent.mkdir(parents=True, exist_ok=True)
    stale_path.write_text("{}", encoding="utf-8")

    result = write_job_manifests(repo_root)

    assert result.plan_path == ".arch/manifests/plan.json"
    assert result.manifest_paths == (
        ".arch/manifests/jobs/compile/compiler_owned.json",
        ".arch/manifests/jobs/unit/payment_service.json",
    )
    assert stale_path.exists() is False
    assert (repo_root / result.plan_path).is_file()
    assert (
        repo_root / ".arch/manifests/jobs/compile/compiler_owned.json"
    ).read_text(encoding="utf-8") == (
        '{\n'
        '  "depends_on": [],\n'
        '  "job_id": "compile:compiler_owned",\n'
        '  "kind": "compile",\n'
        '  "manifest_version": 1,\n'
        '  "owned_files": [\n'
        '    "app/payments/contracts.py",\n'
        '    "app/payments/models.py",\n'
        '    "tests/contracts/test_payment_authorizer.py",\n'
        '    "tests/contracts/test_payment_gateway_contract.py"\n'
        '  ],\n'
        f'  "revision_id": "{result.revision_id}"\n'
        '}\n'
    )
    assert (
        repo_root / ".arch/manifests/jobs/unit/payment_service.json"
    ).read_text(encoding="utf-8") == (
        '{\n'
        '  "depends_on": [\n'
        '    "compile:compiler_owned"\n'
        '  ],\n'
        '  "job_id": "unit:payment_service",\n'
        '  "kind": "implement_unit",\n'
        '  "manifest_version": 1,\n'
        '  "owned_files": [\n'
        '    "app/payments/service.py"\n'
        '  ],\n'
        '  "provided_contracts": [\n'
        '    "payment_authorizer"\n'
        '  ],\n'
        '  "required_contracts": [\n'
        '    "payment_gateway_contract"\n'
        '  ],\n'
        '  "required_units": [\n'
        '    "audit_logger",\n'
        '    "event_bus",\n'
        '    "payment_gateway"\n'
        '  ],\n'
        f'  "revision_id": "{result.revision_id}",\n'
        '  "tests": [\n'
        '    "tests/contracts/test_payment_authorizer.py",\n'
        '    "tests/unit/payments/test_service.py"\n'
        '  ],\n'
        '  "unit_id": "payment_service",\n'
        '  "unit_kind": "service"\n'
        '}\n'
    )


def test_write_job_manifests_respects_target_units(tmp_path: Path) -> None:
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

    result = write_job_manifests(repo_root, target_units=["notification_service"])

    assert result.manifest_paths == (
        ".arch/manifests/jobs/compile/compiler_owned.json",
        ".arch/manifests/jobs/unit/notification_service.json",
    )
    assert (repo_root / ".arch/manifests/jobs/unit/payment_service.json").exists() is False
