"""Minimal revision creation for canonical .arch snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Dict, Mapping

import yaml

from blueprint.ir.validator import ValidationReport, validate_ir


COLLECTION_DIRECTORIES = (
    ("units", "unit"),
    ("contracts", "contract"),
    ("data_models", "data_model"),
    ("flows", "flow"),
)


@dataclass(frozen=True)
class Revision:
    revision_id: str
    snapshot: Dict[str, Any]
    serialized_snapshot: str


class RevisionValidationError(ValueError):
    """Raised when a repo cannot be revisioned because the IR is invalid."""

    def __init__(self, report: ValidationReport) -> None:
        super().__init__("cannot create revision from invalid IR")
        self.report = report


def create_revision(repo_root: Path) -> Revision:
    repo_root = Path(repo_root).resolve()
    report = validate_ir(repo_root)
    if not report.ok:
        raise RevisionValidationError(report)

    snapshot = build_snapshot(repo_root)
    serialized_snapshot = serialize_snapshot(snapshot)
    revision_id = sha256(serialized_snapshot.encode("utf-8")).hexdigest()
    return Revision(
        revision_id=revision_id,
        snapshot=snapshot,
        serialized_snapshot=serialized_snapshot,
    )


def build_snapshot(repo_root: Path) -> Dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    arch_root = repo_root / ".arch"

    system = _normalize_system(_load_yaml(arch_root / "system.yaml"))
    ownership = _normalize_ownership(_load_yaml(arch_root / "ownership.yaml"))
    policies = _normalize_policies(_load_yaml(arch_root / "policies.yaml"))

    collections: Dict[str, list[dict[str, Any]]] = {}
    for directory, kind in COLLECTION_DIRECTORIES:
        entries = []
        for path in sorted((arch_root / directory).glob("*.yaml")):
            entries.append(_normalize_entity(kind, _load_yaml(path)))
        collections[directory] = sorted(entries, key=lambda item: item["id"])

    return {
        "schema_version": system["schema_version"],
        "system": system,
        "collections": collections,
        "ownership": ownership,
        "policies": policies,
    }


def serialize_snapshot(snapshot: Mapping[str, Any]) -> str:
    return json.dumps(snapshot, indent=2, sort_keys=True) + "\n"


def _load_yaml(path: Path) -> dict[str, Any]:
    content = yaml.safe_load(path.read_text(encoding="utf-8"))
    if content is None:
        return {}
    if not isinstance(content, dict):
        raise TypeError(f"expected mapping at {path}")
    return content


def _normalize_system(document: Mapping[str, Any]) -> Dict[str, Any]:
    return _normalize_mapping(document)


def _normalize_ownership(document: Mapping[str, Any]) -> Dict[str, Any]:
    normalized = _normalize_mapping(document)
    normalized["compiler_files"] = sorted(_as_string_list(normalized.get("compiler_files")))
    normalized["unit_files"] = {
        unit_id: sorted(_as_string_list(files))
        for unit_id, files in sorted(_as_mapping(normalized.get("unit_files")).items())
        if isinstance(unit_id, str)
    }
    return normalized


def _normalize_policies(document: Mapping[str, Any]) -> Dict[str, Any]:
    normalized = _normalize_mapping(document)
    normalized["layers"] = sorted(_as_string_list(normalized.get("layers")))
    normalized["forbidden_imports"] = sorted(_as_string_list(normalized.get("forbidden_imports")))
    normalized["allowed_dependencies"] = {
        layer: sorted(_as_string_list(targets))
        for layer, targets in sorted(_as_mapping(normalized.get("allowed_dependencies")).items())
        if isinstance(layer, str)
    }
    return normalized


def _normalize_entity(kind: str, document: Mapping[str, Any]) -> Dict[str, Any]:
    normalized = _normalize_mapping(document)
    normalized.pop("__file__", None)
    normalized["identity"] = _build_identity(kind, normalized)

    if kind == "unit":
        for key in ("events", "files", "provides", "requires", "patterns", "tests"):
            normalized[key] = sorted(_as_string_list(normalized.get(key)))
    elif kind == "contract":
        normalized["methods"] = [
            _normalize_method(method)
            for method in _as_list(normalized.get("methods"))
            if isinstance(method, Mapping)
        ]
    elif kind == "data_model":
        normalized["fields"] = [
            _normalize_field(field)
            for field in _as_list(normalized.get("fields"))
            if isinstance(field, Mapping)
        ]
    elif kind == "flow":
        normalized["trigger"] = _normalize_mapping(_as_mapping(normalized.get("trigger")))
        normalized["steps"] = [
            _normalize_mapping(step)
            for step in _as_list(normalized.get("steps"))
            if isinstance(step, Mapping)
        ]

    return normalized


def _build_identity(kind: str, document: Mapping[str, Any]) -> Dict[str, str]:
    entity_id = _as_string(document.get("id")) or "<unknown>"
    identity = {"entity_id": f"{kind}:{entity_id}"}

    module_path = _as_string(document.get("module"))
    symbol_name = _as_string(document.get("symbol"))
    if module_path and symbol_name:
        identity["symbol_id"] = f"python:{module_path}:{symbol_name}"

    return identity


def _normalize_method(method: Mapping[str, Any]) -> Dict[str, Any]:
    normalized = _normalize_mapping(method)
    normalized["params"] = [
        _normalize_mapping(param)
        for param in _as_list(normalized.get("params"))
        if isinstance(param, Mapping)
    ]
    return normalized


def _normalize_field(field: Mapping[str, Any]) -> Dict[str, Any]:
    return _normalize_mapping(field)


def _normalize_mapping(document: Mapping[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for key, value in document.items():
        if key == "__file__":
            continue
        normalized[key] = _normalize_value(value)
    return normalized


def _normalize_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _normalize_value(subvalue)
            for key, subvalue in sorted(value.items())
            if isinstance(key, str)
        }
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    return value


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _as_string(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]
