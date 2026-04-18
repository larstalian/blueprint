from pathlib import Path
from textwrap import dedent

from blueprint.ir.validator import validate_ir


def test_validate_ir_accepts_valid_repo(tmp_path: Path) -> None:
    write_minimal_repo(tmp_path)

    report = validate_ir(tmp_path)

    assert report.ok, report.diagnostics


def test_validate_ir_reports_stable_diagnostic_codes(tmp_path: Path) -> None:
    write_minimal_repo(tmp_path)
    write_file(
        tmp_path / ".arch/contracts/payment_authorizer.yaml",
        """
        id: payment_authorizer
        kind: protocol
        module: app/payments/service.py
        symbol: PaymentAuthorizer
        methods:
          - name: authorize
            params:
              - name: request
                type: MissingRequest
            returns: PaymentResult
        """,
    )

    report = validate_ir(tmp_path)

    assert not report.ok
    codes = {item.code for item in report.diagnostics}
    assert "ir.compiler_ownership" in codes
    assert "ir.unknown_type" in codes


def test_validate_ir_rejects_ownership_drift(tmp_path: Path) -> None:
    write_minimal_repo(tmp_path)
    write_file(
        tmp_path / ".arch/ownership.yaml",
        """
        unit_files:
          payment_service:
            - app/payments/wrong.py
        compiler_files:
          - app/payments/contracts.py
          - app/payments/models.py
          - tests/contracts/test_payment_authorizer.py
        """,
    )

    report = validate_ir(tmp_path)

    assert not report.ok
    assert any("unit_files must match the files" in item.message for item in report.diagnostics)


def test_validate_ir_rejects_unknown_contract_type_reference(tmp_path: Path) -> None:
    write_minimal_repo(tmp_path)
    write_file(
        tmp_path / ".arch/contracts/payment_authorizer.yaml",
        """
        id: payment_authorizer
        kind: protocol
        module: app/payments/contracts.py
        symbol: PaymentAuthorizer
        methods:
          - name: authorize
            params:
              - name: request
                type: MissingRequest
            returns: PaymentResult
        """,
    )

    report = validate_ir(tmp_path)

    assert not report.ok
    assert any("unknown type 'MissingRequest'" in item.message for item in report.diagnostics)


def test_validate_ir_rejects_disallowed_layer_dependency(tmp_path: Path) -> None:
    write_minimal_repo(tmp_path)
    write_file(
        tmp_path / ".arch/units/payment_gateway.yaml",
        """
        id: payment_gateway
        kind: adapter
        language: python
        generation_mode: opaque
        layer: service
        files:
          - app/payments/gateway.py
        """,
    )

    report = validate_ir(tmp_path)

    assert not report.ok
    assert any("cannot depend on" in item.message for item in report.diagnostics)


def test_validate_ir_rejects_missing_dependency_rule_for_used_layer(tmp_path: Path) -> None:
    write_minimal_repo(tmp_path)
    write_file(
        tmp_path / ".arch/policies.yaml",
        """
        layers:
          - service
          - infra
        allowed_dependencies:
          infra: []
        forbidden_imports:
          - flask
        side_effect_defaults:
          network: false
          filesystem: false
        """,
    )

    report = validate_ir(tmp_path)

    assert not report.ok
    assert any("missing dependency rule for layer 'service'" in item.message for item in report.diagnostics)


def test_validate_ir_rejects_contract_module_outside_compiler_files(tmp_path: Path) -> None:
    write_minimal_repo(tmp_path)
    write_file(
        tmp_path / ".arch/contracts/payment_authorizer.yaml",
        """
        id: payment_authorizer
        kind: protocol
        module: app/payments/service.py
        symbol: PaymentAuthorizer
        methods:
          - name: authorize
            params:
              - name: request
                type: PaymentRequest
            returns: PaymentResult
        """,
    )

    report = validate_ir(tmp_path)

    assert not report.ok
    assert any("must be compiler-owned" in item.message for item in report.diagnostics)


def test_validate_ir_rejects_data_model_module_overlapping_unit_file(tmp_path: Path) -> None:
    write_minimal_repo(tmp_path)
    write_file(
        tmp_path / ".arch/data_models/payment_result.yaml",
        """
        id: payment_result
        kind: dataclass
        module: app/audit/logger.py
        symbol: PaymentResult
        fields:
          - name: accepted
            type: bool
          - name: reason
            type: str
        """,
    )
    write_file(
        tmp_path / ".arch/ownership.yaml",
        """
        unit_files:
          payment_service:
            - app/payments/service.py
        compiler_files:
          - app/payments/contracts.py
          - app/payments/models.py
          - app/audit/logger.py
          - tests/contracts/test_payment_authorizer.py
        """,
    )

    report = validate_ir(tmp_path)

    assert not report.ok
    assert any("cannot overlap unit-owned file" in item.message for item in report.diagnostics)


def test_validate_ir_rejects_unknown_flow_call_method(tmp_path: Path) -> None:
    write_minimal_repo(tmp_path)
    write_file(
        tmp_path / ".arch/flows/checkout_flow.yaml",
        """
        id: checkout_flow
        trigger:
          type: call
          unit: payment_service
          contract: payment_authorizer
        steps:
          - call: payment_service.refund
          - emit: payment_authorized
        """,
    )

    report = validate_ir(tmp_path)

    assert not report.ok
    assert any("does not match any provided contract method" in item.message for item in report.diagnostics)


def test_validate_ir_keeps_cross_file_checks_when_schema_errors_exist(tmp_path: Path) -> None:
    write_minimal_repo(tmp_path)
    write_file(
        tmp_path / ".arch/units/payment_gateway.yaml",
        """
        id: payment_gateway
        kind: adapter
        language: python
        generation_mode: managed
        layer: infra
        files:
          - app/payments/service.py
        unexpected: true
        """,
    )

    report = validate_ir(tmp_path)

    assert not report.ok
    messages = [item.message for item in report.diagnostics]
    assert any("Additional properties are not allowed" in message for message in messages)
    assert any("already owned by managed unit" in message for message in messages)


def test_validate_ir_rejects_invalid_compiler_lock_timestamp(tmp_path: Path) -> None:
    write_minimal_repo(tmp_path)
    write_file(
        tmp_path / ".arch/manifests/compiler.lock.json",
        """
        revision_id: 9e0d5b
        compiler_version: 0.1.0
        repo_commit: abc123
        generated_at: not-a-timestamp
        """,
    )

    report = validate_ir(tmp_path)

    assert not report.ok
    assert any("is not a 'date-time'" in item.message for item in report.diagnostics)


def write_minimal_repo(root: Path) -> None:
    write_file(
        root / ".arch/system.yaml",
        """
        schema_version: 1
        system_id: checkout
        language: python
        python:
          version: "3.13"
          package_root: app
        compiler:
          generated_root: app
          tests_root: tests
        conventions:
          test_framework: pytest
          type_checker: pyright
          formatter: ruff
        """,
    )
    write_file(
        root / ".arch/units/payment_service.yaml",
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
          - protocol_contract
        tests:
          - tests/unit/payments/test_service.py
          - tests/contracts/test_payment_authorizer.py
        policies:
          side_effects:
            network: true
            filesystem: false
          concurrency: sync
        """,
    )
    write_file(
        root / ".arch/units/payment_gateway.yaml",
        """
        id: payment_gateway
        kind: adapter
        language: python
        generation_mode: opaque
        layer: infra
        files:
          - app/payments/gateway.py
        """,
    )
    write_file(
        root / ".arch/units/audit_logger.yaml",
        """
        id: audit_logger
        kind: adapter
        language: python
        generation_mode: observed
        layer: infra
        files:
          - app/audit/logger.py
        """,
    )
    write_file(
        root / ".arch/units/event_bus.yaml",
        """
        id: event_bus
        kind: registry
        language: python
        generation_mode: opaque
        layer: infra
        files:
          - app/events/bus.py
        """,
    )
    write_file(
        root / ".arch/contracts/payment_authorizer.yaml",
        """
        id: payment_authorizer
        kind: protocol
        module: app/payments/contracts.py
        symbol: PaymentAuthorizer
        methods:
          - name: authorize
            params:
              - name: request
                type: PaymentRequest
            returns: PaymentResult
        """,
    )
    write_file(
        root / ".arch/data_models/payment_request.yaml",
        """
        id: payment_request
        kind: dataclass
        module: app/payments/models.py
        symbol: PaymentRequest
        fields:
          - name: amount
            type: Decimal
          - name: currency
            type: str
        """,
    )
    write_file(
        root / ".arch/data_models/payment_result.yaml",
        """
        id: payment_result
        kind: dataclass
        module: app/payments/models.py
        symbol: PaymentResult
        fields:
          - name: accepted
            type: bool
          - name: reason
            type: str
        """,
    )
    write_file(
        root / ".arch/flows/checkout_flow.yaml",
        """
        id: checkout_flow
        trigger:
          type: call
          unit: payment_service
          contract: payment_authorizer
        steps:
          - call: payment_service.authorize
          - emit: payment_authorized
          - call: audit_logger.record
        """,
    )
    write_file(
        root / ".arch/ownership.yaml",
        """
        unit_files:
          payment_service:
            - app/payments/service.py
        compiler_files:
          - app/payments/contracts.py
          - app/payments/models.py
          - tests/contracts/test_payment_authorizer.py
        """,
    )
    write_file(
        root / ".arch/policies.yaml",
        """
        layers:
          - service
          - infra
        allowed_dependencies:
          service:
            - infra
          infra: []
        forbidden_imports:
          - flask
        side_effect_defaults:
          network: false
          filesystem: false
        """,
    )


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(content).lstrip(), encoding="utf-8")
