from pathlib import Path
import shutil

import yaml

from blueprint.planner import plan_jobs


FIXTURES_ROOT = Path(__file__).parent / "fixtures"


def test_plan_jobs_is_stable_for_reordered_equivalent_repos() -> None:
    left = plan_jobs(FIXTURES_ROOT / "minimal_valid_repo")
    right = plan_jobs(FIXTURES_ROOT / "minimal_valid_repo_reordered")

    assert left.revision_id == right.revision_id
    assert left.serialized_plan == right.serialized_plan


def test_plan_jobs_emits_compile_and_managed_unit_jobs() -> None:
    plan = plan_jobs(FIXTURES_ROOT / "minimal_valid_repo")

    assert plan.snapshot == {
        "jobs": [
            {
                "depends_on": [],
                "job_id": "compile:compiler_owned",
                "kind": "compile",
                "owned_files": [
                    "app/payments/contracts.py",
                    "app/payments/models.py",
                    "tests/contracts/test_payment_authorizer.py",
                    "tests/contracts/test_payment_gateway_contract.py",
                ],
            },
            {
                "depends_on": ["compile:compiler_owned"],
                "job_id": "unit:payment_service",
                "kind": "implement_unit",
                "owned_files": ["app/payments/service.py"],
                "provided_contracts": ["payment_authorizer"],
                "required_contracts": ["payment_gateway_contract"],
                "required_units": ["audit_logger", "event_bus", "payment_gateway"],
                "tests": [
                    "tests/contracts/test_payment_authorizer.py",
                    "tests/unit/payments/test_service.py",
                ],
                "unit_id": "payment_service",
                "unit_kind": "service",
            },
        ],
        "revision_id": plan.revision_id,
    }


def test_plan_jobs_can_target_subset_of_managed_units(tmp_path: Path) -> None:
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

    plan = plan_jobs(repo_root, target_units=["notification_service"])

    assert [job["job_id"] for job in plan.snapshot["jobs"]] == [
        "compile:compiler_owned",
        "unit:notification_service",
    ]


def test_plan_jobs_does_not_expand_targets_through_consumed_contracts(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    shutil.copytree(FIXTURES_ROOT / "minimal_valid_repo", repo_root)

    gateway_path = repo_root / ".arch/units/payment_gateway.yaml"
    gateway = yaml.safe_load(gateway_path.read_text(encoding="utf-8"))
    gateway["generation_mode"] = "managed"
    gateway_path.write_text(yaml.safe_dump(gateway, sort_keys=False), encoding="utf-8")

    ownership_path = repo_root / ".arch/ownership.yaml"
    ownership = yaml.safe_load(ownership_path.read_text(encoding="utf-8"))
    ownership["unit_files"]["payment_gateway"] = ["app/payments/gateway.py"]
    ownership_path.write_text(yaml.safe_dump(ownership, sort_keys=False), encoding="utf-8")

    plan = plan_jobs(repo_root, target_units=["payment_service"])

    assert [job["job_id"] for job in plan.snapshot["jobs"]] == [
        "compile:compiler_owned",
        "unit:payment_service",
    ]
