"""Validation for the canonical .arch model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from importlib import resources
import json
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional

from jsonschema import Draft202012Validator, FormatChecker
import yaml


REQUIRED_COLLECTIONS = (
    ("units", "unit"),
    ("contracts", "contract"),
    ("data_models", "data_model"),
    ("flows", "flow"),
)
OPTIONAL_FILES = (("manifests/compiler.lock.json", "compiler_lock"),)

BUILTIN_TYPE_NAMES = {
    "Any",
    "Decimal",
    "Literal",
    "Mapping",
    "None",
    "Optional",
    "Sequence",
    "Union",
    "bool",
    "bytes",
    "dict",
    "float",
    "frozenset",
    "int",
    "list",
    "set",
    "str",
    "tuple",
}
TYPE_NAME_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")


@dataclass(frozen=True)
class Diagnostic:
    path: str
    message: str


@dataclass
class ValidationReport:
    diagnostics: List[Diagnostic] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.diagnostics

    def add(self, path: str, message: str) -> None:
        self.diagnostics.append(Diagnostic(path=path, message=message))


def validate_ir(repo_root: Path) -> ValidationReport:
    repo_root = Path(repo_root).resolve()
    arch_root = repo_root / ".arch"
    report = ValidationReport()

    if not arch_root.is_dir():
        report.add(".arch", "missing .arch directory")
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
        report.add(_relative_path(path, repo_root), "missing required file")
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
        report.add(_relative_path(directory, repo_root), "missing required directory")
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
        report.add(_relative_path(path, repo_root), f"could not read file: {exc}")
        return None

    try:
        document = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        report.add(_relative_path(path, repo_root), f"invalid YAML: {exc}")
        return None

    if document is None:
        document = {}

    if not isinstance(document, dict):
        report.add(_relative_path(path, repo_root), "root document must be a mapping")
        return None

    validator = _schema_validator(schema_name)
    for error in sorted(validator.iter_errors(document), key=_schema_error_sort_key):
        location = _format_schema_error_path(path, repo_root, error.path)
        report.add(location, error.message)

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

    units_by_id = {
        document["id"]: document
        for document in units
        if isinstance(document.get("id"), str)
    }
    contracts_by_id = {
        document["id"]: document
        for document in contracts
        if isinstance(document.get("id"), str)
    }
    data_model_symbols = {
        document["symbol"]
        for document in data_models
        if isinstance(document.get("symbol"), str)
    }
    unit_ids = set(units_by_id)
    contract_ids = set(contracts_by_id)

    managed_unit_files: Dict[str, str] = {}
    for unit in units:
        unit_id = unit.get("id")
        if not unit_id:
            continue

        if unit.get("generation_mode") == "managed":
            for owned_file in _as_string_list(unit.get("files")):
                owner = managed_unit_files.get(owned_file)
                if owner is not None:
                    report.add(
                        unit["__file__"],
                        f"file '{owned_file}' is already owned by managed unit '{owner}'",
                    )
                    continue
                managed_unit_files[owned_file] = unit_id

        for contract_id in _as_string_list(unit.get("provides")):
            if contract_id not in contract_ids:
                report.add(
                    unit["__file__"],
                    f"unknown provided contract '{contract_id}'",
                )

        for dependency_id in _as_string_list(unit.get("requires")):
            if dependency_id not in unit_ids:
                report.add(
                    unit["__file__"],
                    f"unknown required unit '{dependency_id}'",
                )

    ownership_unit_files = _as_mapping(ownership_doc.get("unit_files"))
    flattened_ownership: Dict[str, str] = {}
    for unit_id, files in ownership_unit_files.items():
        if not isinstance(unit_id, str):
            continue
        for owned_file in _as_string_list(files):
            owner = flattened_ownership.get(owned_file)
            if owner is not None:
                report.add(
                    ".arch/ownership.yaml",
                    f"file '{owned_file}' is assigned to both '{owner}' and '{unit_id}'",
                )
                continue
            flattened_ownership[owned_file] = unit_id

    compiler_files = set(_as_string_list(ownership_doc.get("compiler_files")))
    overlap = compiler_files.intersection(flattened_ownership)
    for owned_file in sorted(overlap):
        report.add(
            ".arch/ownership.yaml",
            f"file '{owned_file}' cannot be both compiler-owned and unit-owned",
        )

    for contract in contracts:
        module_path = contract.get("module")
        if not module_path:
            continue
        if module_path not in compiler_files:
            report.add(
                contract["__file__"],
                f"contract module '{module_path}' must be compiler-owned",
            )

        for method in _as_list(contract.get("methods")):
            if not isinstance(method, Mapping):
                continue
            for param in _as_list(method.get("params")):
                if not isinstance(param, Mapping):
                    continue
                type_name = param.get("type")
                if not type_name:
                    continue
                _validate_type_expression(
                    report=report,
                    path=contract["__file__"],
                    field=f"method '{method.get('name', '<unknown>')}' parameter '{param.get('name', '<unknown>')}'",
                    expression=type_name,
                    data_model_symbols=data_model_symbols,
                )

            return_type = method.get("returns")
            if return_type:
                _validate_type_expression(
                    report=report,
                    path=contract["__file__"],
                    field=f"method '{method.get('name', '<unknown>')}' return type",
                    expression=return_type,
                    data_model_symbols=data_model_symbols,
                )

    for data_model in data_models:
        module_path = data_model.get("module")
        if not module_path:
            continue
        if module_path not in compiler_files:
            report.add(
                data_model["__file__"],
                f"data model module '{module_path}' must be compiler-owned",
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
            ".arch/ownership.yaml",
            "unit_files must match the managed unit set declared in .arch/units/",
        )

    for unit_id, expected_files in expected_units.items():
        actual_files = actual_units.get(unit_id, [])
        if expected_files != actual_files:
            report.add(
                ".arch/ownership.yaml",
                "unit_files must match the files of each managed unit exactly",
            )

    layers = set(policies_doc.get("layers", []))
    allowed_dependencies = _as_mapping(policies_doc.get("allowed_dependencies"))
    for layer_name, target_layers in allowed_dependencies.items():
        if not isinstance(layer_name, str):
            continue
        if layer_name not in layers:
            report.add(
                ".arch/policies.yaml",
                f"allowed_dependencies source layer '{layer_name}' is not declared in layers",
            )
        for target_layer in _as_string_list(target_layers):
            if target_layer not in layers:
                report.add(
                    ".arch/policies.yaml",
                    f"allowed_dependencies target layer '{target_layer}' is not declared in layers",
                )

    for unit in units:
        unit_id = unit.get("id")
        unit_layer = unit.get("layer")
        if layers and not unit_layer:
            report.add(
                unit["__file__"],
                "layer is required when policies.yaml declares layers",
            )
            continue
        if unit_layer and unit_layer not in layers:
            report.add(
                unit["__file__"],
                f"unknown layer '{unit_layer}'",
            )

        if not unit_id or not unit_layer or unit_layer not in layers:
            continue

        allowed_target_layers = set(allowed_dependencies.get(unit_layer, []))
        for dependency_id in _as_string_list(unit.get("requires")):
            dependency = units_by_id.get(dependency_id)
            if dependency is None:
                continue
            dependency_layer = dependency.get("layer")
            if not dependency_layer:
                report.add(
                    unit["__file__"],
                    f"required unit '{dependency_id}' is missing a layer",
                )
                continue
            if dependency_layer not in allowed_target_layers:
                report.add(
                    unit["__file__"],
                    f"dependency on unit '{dependency_id}' violates layer policy '{unit_layer} -> {dependency_layer}'",
                )

    for flow in flows:
        trigger = _as_mapping(flow.get("trigger"))
        trigger_unit = trigger.get("unit")
        if trigger_unit and trigger_unit not in unit_ids:
            report.add(
                flow["__file__"],
                f"unknown trigger unit '{trigger_unit}'",
            )

        trigger_contract = trigger.get("contract")
        if trigger_contract and trigger_contract not in contract_ids:
            report.add(
                flow["__file__"],
                f"unknown trigger contract '{trigger_contract}'",
            )
        if trigger_unit and trigger_contract and trigger_unit in units_by_id:
            unit_contracts = set(units_by_id[trigger_unit].get("provides", []))
            if trigger_contract not in unit_contracts:
                report.add(
                    flow["__file__"],
                    f"trigger contract '{trigger_contract}' is not provided by unit '{trigger_unit}'",
                )

        for step in _as_list(flow.get("steps")):
            if not isinstance(step, Mapping):
                continue
            if "call" in step:
                call_target = step["call"]
                unit_prefix, separator, method_name = call_target.partition(".")
                if unit_prefix not in unit_ids:
                    report.add(
                        flow["__file__"],
                        f"unknown flow call target '{call_target}'",
                    )
                    continue

                if not separator or not method_name:
                    report.add(
                        flow["__file__"],
                        f"flow call '{call_target}' must be in '<unit>.<method>' form",
                    )
                    continue

                unit_contract_methods = {
                    method.get("name")
                    for contract_id in _as_string_list(units_by_id[unit_prefix].get("provides"))
                    for method in _as_list(contracts_by_id.get(contract_id, {}).get("methods"))
                    if isinstance(method.get("name"), str)
                }
                if unit_contract_methods and method_name not in unit_contract_methods:
                    report.add(
                        flow["__file__"],
                        f"flow call '{call_target}' does not match any provided contract method on unit '{unit_prefix}'",
                    )


def _check_unique_ids(
    report: ValidationReport,
    global_ids: Dict[str, str],
    kind: str,
    documents: Iterable[Mapping[str, Any]],
) -> None:
    for document in documents:
        identifier = document.get("id")
        if not identifier:
            continue

        previous_file = global_ids.get(identifier)
        if previous_file is not None:
            report.add(
                document["__file__"],
                f"duplicate ID '{identifier}' already defined in '{previous_file}'",
            )
            continue
        global_ids[identifier] = document["__file__"]


def _schema_validator(name: str) -> Draft202012Validator:
    schema_path = resources.files("blueprint.schemas.v1").joinpath(f"{name}.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return Draft202012Validator(schema, format_checker=FormatChecker())


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
        report.add(f"{path}#generated_at", f"'{generated_at}' is not a 'date-time'")


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _validate_type_expression(
    report: ValidationReport,
    path: str,
    field: str,
    expression: str,
    data_model_symbols: set[str],
) -> None:
    unknown_names = []
    for name in TYPE_NAME_PATTERN.findall(expression):
        short_name = name.rsplit(".", 1)[-1]
        if short_name in BUILTIN_TYPE_NAMES:
            continue
        if short_name in data_model_symbols:
            continue
        unknown_names.append(name)

    if unknown_names:
        report.add(
            path,
            f"{field} references unknown type(s): {', '.join(sorted(set(unknown_names)))}",
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
