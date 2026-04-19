from pathlib import Path
import shutil
import tempfile

import pytest
import yaml

from blueprint.revisions import RevisionValidationError, create_revision


FIXTURES_ROOT = Path(__file__).parent / "fixtures"


def test_create_revision_is_stable_for_reordered_equivalent_repos() -> None:
    left = create_revision(FIXTURES_ROOT / "minimal_valid_repo")
    right = create_revision(FIXTURES_ROOT / "minimal_valid_repo_reordered")

    assert left.revision_id == right.revision_id
    assert left.serialized_snapshot == right.serialized_snapshot


def test_create_revision_includes_stable_symbol_identity() -> None:
    revision = create_revision(FIXTURES_ROOT / "minimal_valid_repo")

    contracts = revision.snapshot["collections"]["contracts"]
    data_models = revision.snapshot["collections"]["data_models"]

    assert contracts[0]["identity"] == {
        "entity_id": "contract:payment_authorizer",
        "symbol_id": "python:app/payments/contracts.py:PaymentAuthorizer",
    }
    assert data_models[0]["identity"] == {
        "entity_id": "data_model:payment_request",
        "symbol_id": "python:app/payments/models.py:PaymentRequest",
    }


def test_create_revision_rejects_invalid_ir_repo() -> None:
    with pytest.raises(RevisionValidationError) as exc_info:
        create_revision(FIXTURES_ROOT / "invalid_missing_ownership")

    assert any(item.code == "ir.missing_file" for item in exc_info.value.report.diagnostics)


def test_create_revision_normalizes_consumed_contract_order() -> None:
    root = FIXTURES_ROOT / "minimal_valid_repo"
    with tempfile.TemporaryDirectory() as tmpdir:
        left = Path(tmpdir) / "left"
        right = Path(tmpdir) / "right"
        shutil.copytree(root, left)
        shutil.copytree(root, right)

        for repo_root, consumed_contracts in (
            (left, ["audit_sink", "payment_gateway_contract"]),
            (right, ["payment_gateway_contract", "audit_sink"]),
        ):
            unit_path = repo_root / ".arch/units/payment_service.yaml"
            unit = yaml.safe_load(unit_path.read_text(encoding="utf-8"))
            unit["consumes"] = consumed_contracts
            unit_path.write_text(yaml.safe_dump(unit, sort_keys=False), encoding="utf-8")

            contract_path = repo_root / ".arch/contracts/audit_sink.yaml"
            contract_path.write_text(
                "\n".join(
                    [
                        "id: audit_sink",
                        "kind: protocol",
                        "module: app/payments/contracts.py",
                        "symbol: AuditSink",
                        "methods: []",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            audit_logger_path = repo_root / ".arch/units/audit_logger.yaml"
            audit_logger = yaml.safe_load(audit_logger_path.read_text(encoding="utf-8"))
            audit_logger["provides"] = ["audit_sink"]
            audit_logger_path.write_text(
                yaml.safe_dump(audit_logger, sort_keys=False),
                encoding="utf-8",
            )

            ownership_path = repo_root / ".arch/ownership.yaml"
            ownership = yaml.safe_load(ownership_path.read_text(encoding="utf-8"))
            ownership["compiler_files"].append("tests/contracts/test_audit_sink.py")
            ownership_path.write_text(yaml.safe_dump(ownership, sort_keys=False), encoding="utf-8")

        left_revision = create_revision(left)
        right_revision = create_revision(right)

    assert left_revision.revision_id == right_revision.revision_id
    assert left_revision.serialized_snapshot == right_revision.serialized_snapshot
