"""Validation for the canonical .arch model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from importlib import resources
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from jsonschema import Draft202012Validator
import yaml

from blueprint.patterns import KNOWN_UNIT_PATTERNS


REQUIRED_COLLECTIONS = (
    ("units", "unit"),
    ("contracts", "contract"),
    ("data_models", "data_model"),
    ("flows", "flow"),
)
OPTIONAL_FILES = (("manifests/compiler.lock.json", "compiler_lock"),)

BUILTIN_TYPE_NAMES = {
    "Decimal",
    "None",
    "bool",
    "bytes",
    "date",
    "datetime",
    "float",
    "int",
    "str",
    "UUID",
}

IR_MISSING_ARCH_ROOT = "ir.missing_arch_root"
IR_MISSING_FILE = "ir.missing_file"
IR_MISSING_DIRECTORY = "ir.missing_directory"
IR_READ_ERROR = "ir.read_error"
IR_INVALID_YAML = "ir.invalid_yaml"
IR_INVALID_ROOT = "ir.invalid_root"
IR_SCHEMA_VIOLATION = "ir.schema_violation"
IR_DUPLICATE_ID = "ir.duplicate_id"
IR_UNKNOWN_CONTRACT = "ir.unknown_contract"
IR_UNKNOWN_UNIT = "ir.unknown_unit"
IR_OWNERSHIP_CONFLICT = "ir.ownership_conflict"
IR_OWNERSHIP_MISMATCH = "ir.ownership_mismatch"
IR_COMPILER_OWNERSHIP = "ir.compiler_ownership"
IR_UNKNOWN_TYPE = "ir.unknown_type"
IR_UNKNOWN_PATTERN = "ir.unknown_pattern"
IR_REGISTRY_EVENT = "ir.registry_event"
IR_POLICY_LAYER = "ir.policy_layer"
IR_FLOW_REFERENCE = "ir.flow_reference"
IR_COMPILER_LOCK_INVALID = "ir.compiler_lock_invalid"


@dataclass(frozen=True)
class Diagnostic:
    code: str
    path: str
    message: str


@dataclass
class ValidationReport:
    diagnostics: List[Diagnostic] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.diagnostics

    def add(self, code: str, path: str, message: str) -> None:
        self.diagnostics.append(Diagnostic(code=code, path=path, message=message))


def validate_ir(repo_root: Path) -> ValidationReport:
    repo_root = Path(repo_root).resolve()
    arch_root = repo_root / ".arch"
    report = ValidationReport()

    if not arch_root.is_dir():
        report.add(IR_MISSING_ARCH_ROOT, ".arch", "missing .arch directory")
        return report

    system_doc = _load_required_document(
        repo_root=repo_root,
        path=arch_root / "system.yaml",
        schema_name="system",
        report=report,
    )
    ownership_doc = _load_required_document(
        repo_root=repo_root,
        path=arch_root / "ownership.yaml",
        schema_name="ownership",
        report=report,
    )
    policies_doc = _load_required_document(
        repo_root=repo_root,
        path=arch_root / "policies.yaml",
        schema_name="policies",
        report=report,
    )

    collections: Dict[str, List[Dict[str, Any]]] = {}
    for directory, schema_name in REQUIRED_COLLECTIONS:
        collection_path = arch_root / directory
        collection_docs = _load_collection(
            repo_root=repo_root,
            directory=collection_path,
            schema_name=schema_name,
            report=report,
        )
        collections[directory] = collection_docs

    for relative_path, schema_name in OPTIONAL_FILES:
        path = arch_root / relative_path
        if path.exists():
            _load_optional_document(
                repo_root=repo_root,
                path=path,
                schema_name=schema_name,
                report=report,
            )

    _validate_cross_file_rules(
        repo_root=repo_root,
        report=report,
        system_doc=system_doc or {},
        ownership_doc=ownership_doc or {},
        policies_doc=policies_doc or {},
        units=collections["units"],
        contracts=collections["contracts"],
        data_models=collections["data_models"],
        flows=collections["flows"],
    )

    return report


def _load_required_document(
    repo_root: Path,
    path: Path,
    schema_name: str,
    report: ValidationReport,
) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        report.add(
            IR_MISSING_FILE,
            _relative_path(path, repo_root),
            "missing required file",
        )
        return None
    return _load_document(repo_root=repo_root, path=path, schema_name=schema_name, report=report)


def _load_optional_document(
    repo_root: Path,
    path: Path,
    schema_name: str,
    report: ValidationReport,
) -> Optional[Dict[str, Any]]:
    return _load_document(repo_root=repo_root, path=path, schema_name=schema_name, report=report)


def _load_collection(
    repo_root: Path,
    directory: Path,
    schema_name: str,
    report: ValidationReport,
) -> List[Dict[str, Any]]:
    if not directory.is_dir():
        report.add(
            IR_MISSING_DIRECTORY,
            _relative_path(directory, repo_root),
            "missing required directory",
        )
        return []

    documents: List[Dict[str, Any]] = []
    for path in sorted(directory.glob("*.yaml")):
        document = _load_document(
            repo_root=repo_root,
            path=path,
            schema_name=schema_name,
            report=report,
        )
        if document is not None:
            documents.append(document)
    return documents


def _load_document(
    repo_root: Path,
    path: Path,
    schema_name: str,
    report: ValidationReport,
) -> Optional[Dict[str, Any]]:
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        report.add(
            IR_READ_ERROR,
            _relative_path(path, repo_root),
            f"could not read file: {exc}",
        )
        return None

    try:
        document = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        report.add(
            IR_INVALID_YAML,
            _relative_path(path, repo_root),
            f"invalid YAML: {exc}",
        )
        return None

    if document is None:
        document = {}

    if not isinstance(document, dict):
        report.add(
            IR_INVALID_ROOT,
            _relative_path(path, repo_root),
            "root document must be a mapping",
        )
        return None

    validator = _schema_validator(schema_name)
    for error in sorted(validator.iter_errors(document), key=_schema_error_sort_key):
        location = _format_schema_error_path(path, repo_root, error.path)
        report.add(IR_SCHEMA_VIOLATION, location, error.message)

    if schema_name == "compiler_lock":
        _validate_compiler_lock_document(
            report=report,
            path=_relative_path(path, repo_root),
            document=document,
        )

    document["__file__"] = _relative_path(path, repo_root)
    return document


def _validate_cross_file_rules(
    repo_root: Path,
    report: ValidationReport,
    system_doc: Mapping[str, Any],
    ownership_doc: Mapping[str, Any],
    policies_doc: Mapping[str, Any],
    units: List[Mapping[str, Any]],
    contracts: List[Mapping[str, Any]],
    data_models: List[Mapping[str, Any]],
    flows: List[Mapping[str, Any]],
) -> None:
    del repo_root
    del system_doc

    global_ids: Dict[str, str] = {}
    for kind, documents in (
        ("unit", units),
        ("contract", contracts),
        ("data_model", data_models),
        ("flow", flows),
    ):
        _check_unique_ids(report, global_ids, kind, documents)

    units_by_id = {}
    unit_layers: Dict[str, Optional[str]] = {}
    unit_files: Dict[str, List[str]] = {}
    for unit in units:
        unit_id = _as_string(unit.get("id"))
        if not unit_id:
            continue
        units_by_id.setdefault(unit_id, unit)
        unit_layers[unit_id] = _as_string(unit.get("layer"))
        for owned_file in _as_string_list(unit.get("files")):
            unit_files.setdefault(owned_file, []).append(unit_id)

    contracts_by_id = {}
    for contract in contracts:
        contract_id = _as_string(contract.get("id"))
        if contract_id:
            contracts_by_id.setdefault(contract_id, contract)

    data_model_symbols = {
        symbol
        for data_model in data_models
        if (symbol := _as_string(data_model.get("symbol"))) is not None
    }
    unit_ids = set(units_by_id)
    contract_ids = set(contracts_by_id)
    registry_unit_ids = {
        unit_id
        for unit_id, unit in units_by_id.items()
        if unit.get("kind") == "registry"
    }
    registry_event_owners: Dict[str, str] = {}
    duplicate_registry_events: set[str] = set()

    managed_unit_files: Dict[str, str] = {}
    for unit in units:
        unit_path = _document_path(unit)
        unit_id = _as_string(unit.get("id"))
        if not unit_id:
            continue

        if unit.get("generation_mode") == "managed":
            for owned_file in _as_string_list(unit.get("files")):
                owner = managed_unit_files.get(owned_file)
                if owner is not None:
                    report.add(
                        IR_OWNERSHIP_CONFLICT,
                        unit_path,
                        f"file '{owned_file}' is already owned by managed unit '{owner}'",
                    )
                    continue
                managed_unit_files[owned_file] = unit_id

        for contract_id in _as_string_list(unit.get("provides")):
            if contract_id not in contract_ids:
                report.add(
                    IR_UNKNOWN_CONTRACT,
                    unit_path,
                    f"unknown provided contract '{contract_id}'",
                )

        for dependency_id in _as_string_list(unit.get("requires")):
            if dependency_id not in unit_ids:
                report.add(
                    IR_UNKNOWN_UNIT,
                    unit_path,
                    f"unknown required unit '{dependency_id}'",
                )

        for pattern_name in _as_string_list(unit.get("patterns")):
            if pattern_name not in KNOWN_UNIT_PATTERNS:
                report.add(
                    IR_UNKNOWN_PATTERN,
                    _path_with_fragment(unit_path, "patterns"),
                    f"unknown unit pattern '{pattern_name}'",
                )

        event_names = _as_string_list(unit.get("events"))
        if event_names and unit.get("kind") != "registry":
            report.add(
                IR_REGISTRY_EVENT,
                _path_with_fragment(unit_path, "events"),
                f"unit '{unit_id}' must have kind 'registry' to declare events",
            )
        if unit_id and unit.get("kind") == "registry":
            for event_name in event_names:
                owner = registry_event_owners.get(event_name)
                if owner is not None:
                    duplicate_registry_events.add(event_name)
                    report.add(
                        IR_REGISTRY_EVENT,
                        _path_with_fragment(unit_path, "events"),
                        (
                            f"registry event '{event_name}' is already declared by "
                            f"registry unit '{owner}'"
                        ),
                    )
                    continue
                registry_event_owners[event_name] = unit_id

    ownership_unit_files = _as_mapping(ownership_doc.get("unit_files"))
    flattened_ownership: Dict[str, str] = {}
    for unit_id, files in ownership_unit_files.items():
        if not isinstance(unit_id, str):
            continue
        for owned_file in _as_string_list(files):
            owner = flattened_ownership.get(owned_file)
            if owner is not None:
                report.add(
                    IR_OWNERSHIP_CONFLICT,
                    ".arch/ownership.yaml",
                    f"file '{owned_file}' is assigned to both '{owner}' and '{unit_id}'",
                )
                continue
            flattened_ownership[owned_file] = unit_id

    compiler_files = set(_as_string_list(ownership_doc.get("compiler_files")))
    overlap = compiler_files.intersection(flattened_ownership)
    for owned_file in sorted(overlap):
        report.add(
            IR_OWNERSHIP_CONFLICT,
            ".arch/ownership.yaml",
            f"file '{owned_file}' cannot be both compiler-owned and unit-owned",
        )

    for contract in contracts:
        contract_path = _document_path(contract)
        module_path = _as_string(contract.get("module"))
        if not module_path:
            continue
        if module_path not in compiler_files:
            report.add(
                IR_COMPILER_OWNERSHIP,
                _path_with_fragment(contract_path, "module"),
                f"contract module '{module_path}' must be compiler-owned",
            )
        overlapping_units = sorted(set(unit_files.get(module_path, [])))
        if overlapping_units:
            report.add(
                IR_COMPILER_OWNERSHIP,
                _path_with_fragment(contract_path, "module"),
                (
                    f"contract module '{module_path}' cannot overlap unit-owned file(s): "
                    f"{', '.join(overlapping_units)}"
                ),
            )

        for method_index, method in enumerate(_as_list(contract.get("methods"))):
            if not isinstance(method, Mapping):
                continue
            method_name = _as_string(method.get("name")) or "<unknown>"
            for param_index, param in enumerate(_as_list(method.get("params"))):
                if not isinstance(param, Mapping):
                    continue
                type_name = _as_string(param.get("type"))
                if not type_name:
                    continue
                _validate_type_expression(
                    report=report,
                    path=_path_with_fragment(
                        contract_path,
                        "methods",
                        method_index,
                        "params",
                        param_index,
                        "type",
                    ),
                    field=(
                        f"method '{method_name}' parameter "
                        f"'{_as_string(param.get('name')) or '<unknown>'}'"
                    ),
                    expression=type_name,
                    data_model_symbols=data_model_symbols,
                )

            return_type = _as_string(method.get("returns"))
            if return_type:
                _validate_type_expression(
                    report=report,
                    path=_path_with_fragment(contract_path, "methods", method_index, "returns"),
                    field=f"method '{method_name}' return type",
                    expression=return_type,
                    data_model_symbols=data_model_symbols,
                )

    for data_model in data_models:
        data_model_path = _document_path(data_model)
        module_path = _as_string(data_model.get("module"))
        if not module_path:
            continue
        if module_path not in compiler_files:
            report.add(
                IR_COMPILER_OWNERSHIP,
                _path_with_fragment(data_model_path, "module"),
                f"data model module '{module_path}' must be compiler-owned",
            )
        overlapping_units = sorted(set(unit_files.get(module_path, [])))
        if overlapping_units:
            report.add(
                IR_COMPILER_OWNERSHIP,
                _path_with_fragment(data_model_path, "module"),
                (
                    f"data model module '{module_path}' cannot overlap unit-owned file(s): "
                    f"{', '.join(overlapping_units)}"
                ),
            )

    expected_units = {
        unit_id: sorted(
            owned_file
            for owned_file, owner in managed_unit_files.items()
            if owner == unit_id
        )
        for unit_id in sorted(set(managed_unit_files.values()))
    }
    actual_units = {
        unit_id: sorted(_as_string_list(files))
        for unit_id, files in ownership_unit_files.items()
        if isinstance(unit_id, str)
    }

    if set(expected_units) != set(actual_units):
        report.add(
            IR_OWNERSHIP_MISMATCH,
            ".arch/ownership.yaml",
            "unit_files must match the managed unit set declared in .arch/units/",
        )

    for unit_id, expected_files in expected_units.items():
        actual_files = actual_units.get(unit_id, [])
        if expected_files != actual_files:
            report.add(
                IR_OWNERSHIP_MISMATCH,
                ".arch/ownership.yaml",
                "unit_files must match the files of each managed unit exactly",
            )

    policies_path = _document_path(policies_doc, ".arch/policies.yaml")
    layers = set(_as_string_list(policies_doc.get("layers")))
    allowed_dependencies = {
        layer_name: _as_string_list(target_layers)
        for layer_name, target_layers in _as_mapping(policies_doc.get("allowed_dependencies")).items()
        if isinstance(layer_name, str)
    }
    for layer_name, target_layers in allowed_dependencies.items():
        if layer_name not in layers:
            report.add(
                IR_POLICY_LAYER,
                _path_with_fragment(policies_path, "allowed_dependencies", layer_name),
                f"allowed_dependencies source layer '{layer_name}' is not declared in layers",
            )
        for target_layer in target_layers:
            if target_layer not in layers:
                report.add(
                    IR_POLICY_LAYER,
                    _path_with_fragment(policies_path, "allowed_dependencies", layer_name),
                    f"allowed_dependencies target layer '{target_layer}' is not declared in layers",
                )

    for used_layer in sorted(
        {
            unit_layer
            for unit_layer in unit_layers.values()
            if unit_layer is not None and unit_layer in layers
        }
    ):
        if used_layer not in allowed_dependencies:
            report.add(
                IR_POLICY_LAYER,
                _path_with_fragment(policies_path, "allowed_dependencies"),
                f"missing dependency rule for layer '{used_layer}'",
            )

    for unit in units:
        unit_path = _document_path(unit)
        unit_id = _as_string(unit.get("id"))
        unit_layer = _as_string(unit.get("layer"))
        if layers and not unit_layer:
            report.add(
                IR_POLICY_LAYER,
                unit_path,
                "layer is required when dependency policies are defined",
            )
            continue
        if unit_layer and unit_layer not in layers:
            report.add(
                IR_POLICY_LAYER,
                _path_with_fragment(unit_path, "layer"),
                f"unknown layer '{unit_layer}'",
            )

        if not unit_id or not unit_layer or unit_layer not in layers:
            continue

        if unit_layer not in allowed_dependencies:
            continue

        allowed_target_layers = set(allowed_dependencies.get(unit_layer, []))
        for dependency_id in _as_string_list(unit.get("requires")):
            dependency_layer = unit_layers.get(dependency_id)
            if not dependency_layer:
                report.add(
                    IR_POLICY_LAYER,
                    unit_path,
                    f"required unit '{dependency_id}' is missing a layer",
                )
                continue
            if dependency_layer not in allowed_target_layers:
                report.add(
                    IR_POLICY_LAYER,
                    unit_path,
                    (
                        f"unit '{unit_id}' in layer '{unit_layer}' cannot depend on "
                        f"'{dependency_id}' in layer '{dependency_layer}'"
                    ),
                )

    for flow in flows:
        flow_path = _document_path(flow)
        trigger = _as_mapping(flow.get("trigger"))
        trigger_unit = _as_string(trigger.get("unit"))
        if trigger_unit and trigger_unit not in unit_ids:
            report.add(
                IR_FLOW_REFERENCE,
                _path_with_fragment(flow_path, "trigger", "unit"),
                f"unknown trigger unit '{trigger_unit}'",
            )

        trigger_contract = _as_string(trigger.get("contract"))
        if trigger_contract and trigger_contract not in contract_ids:
            report.add(
                IR_FLOW_REFERENCE,
                _path_with_fragment(flow_path, "trigger", "contract"),
                f"unknown trigger contract '{trigger_contract}'",
            )
        if (
            trigger_unit
            and trigger_contract
            and trigger_unit in units_by_id
            and trigger_contract in contract_ids
        ):
            provided_contracts = set(_as_string_list(units_by_id[trigger_unit].get("provides")))
            if trigger_contract not in provided_contracts:
                report.add(
                    IR_FLOW_REFERENCE,
                    _path_with_fragment(flow_path, "trigger", "contract"),
                    f"trigger contract '{trigger_contract}' is not provided by unit '{trigger_unit}'",
                )

        for step_index, step in enumerate(_as_list(flow.get("steps"))):
            if not isinstance(step, Mapping):
                continue
            call_target = _as_string(step.get("call"))
            if call_target:
                unit_prefix, separator, method_name = call_target.partition(".")
                if not separator or not unit_prefix or not method_name:
                    report.add(
                        IR_FLOW_REFERENCE,
                        _path_with_fragment(flow_path, "steps", step_index, "call"),
                        f"flow call '{call_target}' must be in '<unit>.<method>' form",
                    )
                    continue

                if unit_prefix not in unit_ids:
                    report.add(
                        IR_FLOW_REFERENCE,
                        _path_with_fragment(flow_path, "steps", step_index, "call"),
                        f"unknown flow call target '{call_target}'",
                    )
                    continue

                unit_contract_methods = {
                    contract_method_name
                    for contract_id in _as_string_list(units_by_id[unit_prefix].get("provides"))
                    for method in _as_list(contracts_by_id.get(contract_id, {}).get("methods"))
                    if isinstance(method, Mapping)
                    if (contract_method_name := _as_string(method.get("name"))) is not None
                }
                if unit_contract_methods and method_name not in unit_contract_methods:
                    report.add(
                        IR_FLOW_REFERENCE,
                        _path_with_fragment(flow_path, "steps", step_index, "call"),
                        (
                            f"flow call '{call_target}' does not match any provided contract "
                            f"method on unit '{unit_prefix}'"
                        ),
                    )
                continue

            event_name = _as_string(step.get("emit"))
            if event_name:
                if event_name in duplicate_registry_events:
                    continue
                owner_unit = registry_event_owners.get(event_name)
                if owner_unit is None:
                    report.add(
                        IR_REGISTRY_EVENT,
                        _path_with_fragment(flow_path, "steps", step_index, "emit"),
                        f"unknown registry event '{event_name}'",
                    )
                    continue
                if trigger_unit and trigger_unit in units_by_id:
                    reachable_registry_units = {
                        unit_id
                        for unit_id in _as_string_list(units_by_id[trigger_unit].get("requires"))
                        if unit_id in registry_unit_ids
                    }
                    if trigger_unit in registry_unit_ids:
                        reachable_registry_units.add(trigger_unit)
                    if owner_unit not in reachable_registry_units:
                        report.add(
                            IR_REGISTRY_EVENT,
                            _path_with_fragment(flow_path, "steps", step_index, "emit"),
                            (
                                f"unit '{trigger_unit}' cannot emit registry event '{event_name}' "
                                f"without depending on registry unit '{owner_unit}'"
                            ),
                        )


def _check_unique_ids(
    report: ValidationReport,
    global_ids: Dict[str, str],
    kind: str,
    documents: Iterable[Mapping[str, Any]],
) -> None:
    for document in documents:
        identifier = _as_string(document.get("id"))
        if not identifier:
            continue

        previous_file = global_ids.get(identifier)
        if previous_file is not None:
            report.add(
                IR_DUPLICATE_ID,
                document["__file__"],
                f"duplicate ID '{identifier}' already defined in '{previous_file}'",
            )
            continue
        global_ids[identifier] = document["__file__"]


def _schema_validator(name: str) -> Draft202012Validator:
    schema_path = resources.files("blueprint.schemas.v1").joinpath(f"{name}.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def _validate_compiler_lock_document(
    report: ValidationReport,
    path: str,
    document: Mapping[str, Any],
) -> None:
    generated_at = document.get("generated_at")
    if not isinstance(generated_at, str):
        return

    candidate = generated_at.replace("Z", "+00:00")
    try:
        datetime.fromisoformat(candidate)
    except ValueError:
        report.add(
            IR_COMPILER_LOCK_INVALID,
            f"{path}#generated_at",
            f"'{generated_at}' is not a 'date-time'",
        )


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _as_string(value: Any) -> Optional[str]:
    if isinstance(value, str) and value:
        return value
    return None


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _document_path(document: Mapping[str, Any], default: str = "") -> str:
    path = document.get("__file__")
    if isinstance(path, str):
        return path
    return default


def _path_with_fragment(path: str, *parts: Any) -> str:
    fragment = ".".join(str(part) for part in parts)
    if not fragment:
        return path
    return f"{path}#{fragment}"


def _validate_type_expression(
    report: ValidationReport,
    path: str,
    field: str,
    expression: str,
    data_model_symbols: set[str],
) -> None:
    short_name = expression.rsplit(".", 1)[-1]
    if short_name not in BUILTIN_TYPE_NAMES and short_name not in data_model_symbols:
        report.add(
            IR_UNKNOWN_TYPE,
            path,
            f"{field} references unknown type '{expression}'",
        )


def _schema_error_sort_key(error: Any) -> List[Any]:
    return list(error.path)


def _format_schema_error_path(path: Path, repo_root: Path, schema_path: Iterable[Any]) -> str:
    base = _relative_path(path, repo_root)
    parts = [str(part) for part in schema_path]
    if not parts:
        return base
    return f"{base}#{'.'.join(parts)}"


def _relative_path(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root).as_posix()
