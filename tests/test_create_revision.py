from pathlib import Path

import pytest

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

