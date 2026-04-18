"""Explicit pattern support catalog for the current backend."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PatternSpec:
    id: str
    scope: str
    status: str
    summary: str


PATTERN_SPECS = (
    PatternSpec(
        id="unit.service",
        scope="case_tag",
        status="real",
        summary="Unit kind with planning, ownership, and dependency semantics.",
    ),
    PatternSpec(
        id="unit.adapter",
        scope="case_tag",
        status="real",
        summary="Unit kind with planning, ownership, and dependency semantics.",
    ),
    PatternSpec(
        id="unit.registry",
        scope="case_tag",
        status="metadata",
        summary="Known unit boundary only. No registry-specific compiler or verifier behavior.",
    ),
    PatternSpec(
        id="unit.hook",
        scope="case_tag",
        status="metadata",
        summary="Known unit boundary only. No hook-specific compiler or verifier behavior.",
    ),
    PatternSpec(
        id="unit.event_handler",
        scope="case_tag",
        status="metadata",
        summary="Known unit boundary only. No event-handler-specific compiler or verifier behavior.",
    ),
    PatternSpec(
        id="unit.task",
        scope="case_tag",
        status="metadata",
        summary="Known unit boundary only. No task-specific compiler or verifier behavior.",
    ),
    PatternSpec(
        id="contract.protocol",
        scope="case_tag",
        status="real",
        summary="Compiled and verified as a Python Protocol contract.",
    ),
    PatternSpec(
        id="contract.abc",
        scope="case_tag",
        status="real",
        summary="Compiled and verified as a Python ABC contract.",
    ),
    PatternSpec(
        id="model.dataclass",
        scope="case_tag",
        status="real",
        summary="Compiled and verified as a Python dataclass model.",
    ),
    PatternSpec(
        id="model.typed_dict",
        scope="case_tag",
        status="real",
        summary="Compiled as a Python TypedDict model.",
    ),
    PatternSpec(
        id="flow.call",
        scope="case_tag",
        status="real",
        summary="Validated against unit and provided contract method names.",
    ),
    PatternSpec(
        id="flow.emit",
        scope="case_tag",
        status="metadata",
        summary="Flow syntax only. No event emission semantics are enforced yet.",
    ),
    PatternSpec(
        id="flow.subscribe",
        scope="case_tag",
        status="metadata",
        summary="Flow syntax only. No subscription semantics are enforced yet.",
    ),
    PatternSpec(
        id="policy.layer_rules",
        scope="case_tag",
        status="real",
        summary="Layer dependency rules are enforced during IR validation.",
    ),
    PatternSpec(
        id="ownership.compiler_files",
        scope="case_tag",
        status="real",
        summary="Compiler-owned file boundaries are enforced during IR validation.",
    ),
    PatternSpec(
        id="repo.missing_required_file",
        scope="case_tag",
        status="real",
        summary="Required .arch files and directories are enforced during IR validation.",
    ),
    PatternSpec(
        id="constructor_injection",
        scope="unit_pattern",
        status="metadata",
        summary="Known unit pattern name only. No constructor-injection analysis yet.",
    ),
    PatternSpec(
        id="protocol_contract",
        scope="unit_pattern",
        status="metadata",
        summary="Known unit pattern name only. Contract semantics come from contracts/*.yaml.",
    ),
    PatternSpec(
        id="abc_contract",
        scope="unit_pattern",
        status="metadata",
        summary="Known unit pattern name only. Contract semantics come from contracts/*.yaml.",
    ),
    PatternSpec(
        id="dataclass_model",
        scope="unit_pattern",
        status="metadata",
        summary="Known unit pattern name only. Model semantics come from data_models/*.yaml.",
    ),
    PatternSpec(
        id="typed_dict_model",
        scope="unit_pattern",
        status="metadata",
        summary="Known unit pattern name only. Model semantics come from data_models/*.yaml.",
    ),
    PatternSpec(
        id="registry",
        scope="unit_pattern",
        status="metadata",
        summary="Known unit pattern name only. No registry adapter exists yet.",
    ),
    PatternSpec(
        id="hook",
        scope="unit_pattern",
        status="metadata",
        summary="Known unit pattern name only. No hook adapter exists yet.",
    ),
    PatternSpec(
        id="event_handler",
        scope="unit_pattern",
        status="metadata",
        summary="Known unit pattern name only. No event handler adapter exists yet.",
    ),
    PatternSpec(
        id="cli_command",
        scope="unit_pattern",
        status="metadata",
        summary="Known unit pattern name only. No CLI command adapter exists yet.",
    ),
)

PATTERN_SPECS_BY_ID = {spec.id: spec for spec in PATTERN_SPECS}
KNOWN_CASE_PATTERNS = frozenset(spec.id for spec in PATTERN_SPECS if spec.scope == "case_tag")
KNOWN_UNIT_PATTERNS = frozenset(spec.id for spec in PATTERN_SPECS if spec.scope == "unit_pattern")
