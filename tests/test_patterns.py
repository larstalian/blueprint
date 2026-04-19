from pathlib import Path
import shutil
from textwrap import dedent

import yaml

from blueprint.ir.validator import validate_ir
from blueprint.patterns import KNOWN_CASE_PATTERNS, PATTERN_SPECS


CASES_ROOT = Path(__file__).parent / "conformance" / "cases"
FIXTURES_ROOT = Path(__file__).parent / "fixtures"
MATRIX_PATH = Path(__file__).parent.parent / "docs" / "pattern-support-matrix.md"


def test_validate_ir_rejects_unknown_unit_pattern(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    shutil.copytree(FIXTURES_ROOT / "minimal_valid_repo", repo_root)
    (repo_root / ".arch/units/payment_service.yaml").write_text(
        dedent(
            """
        id: payment_service
        kind: service
        language: python
        generation_mode: managed
        layer: service
        files:
          - app/payments/service.py
        provides:
          - payment_authorizer
        requires:
          - payment_gateway
          - audit_logger
          - event_bus
        patterns:
          - constructor_injection
          - unknown_magic
        tests:
          - tests/unit/payments/test_service.py
          - tests/contracts/test_payment_authorizer.py
        policies:
          side_effects:
            network: true
            filesystem: false
          concurrency: sync
        """
        ).lstrip(),
        encoding="utf-8",
    )

    report = validate_ir(repo_root)

    assert not report.ok
    assert [
        diagnostic.code
        for diagnostic in report.diagnostics
        if diagnostic.code == "ir.unknown_pattern"
    ] == ["ir.unknown_pattern"]


def test_pattern_catalog_covers_conformance_cases_and_matrix_doc() -> None:
    matrix_text = MATRIX_PATH.read_text(encoding="utf-8")

    for spec in PATTERN_SPECS:
        assert spec.id in matrix_text

    for case_dir in sorted(CASES_ROOT.iterdir()):
        if not case_dir.is_dir():
            continue
        case = yaml.safe_load((case_dir / "case.yaml").read_text(encoding="utf-8"))
        for pattern_id in case.get("patterns", []):
            assert pattern_id in KNOWN_CASE_PATTERNS, f"{case['id']}: unknown pattern tag {pattern_id}"
