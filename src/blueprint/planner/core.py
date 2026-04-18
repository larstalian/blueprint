"""Deterministic planning from canonical revision snapshots."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Dict, Mapping

from blueprint.revisions import Revision, create_revision


@dataclass(frozen=True)
class Plan:
    revision_id: str
    snapshot: Dict[str, Any]
    serialized_plan: str


def plan_jobs(repo_root: Path, target_units: list[str] | None = None) -> Plan:
    repo_root = Path(repo_root).resolve()
    revision = create_revision(repo_root)
    snapshot = build_plan_snapshot(revision, target_units=target_units)
    serialized_plan = serialize_plan(snapshot)
    return Plan(
        revision_id=revision.revision_id,
        snapshot=snapshot,
        serialized_plan=serialized_plan,
    )


def build_plan_snapshot(
    revision: Revision,
    target_units: list[str] | None = None,
) -> Dict[str, Any]:
    snapshot = revision.snapshot
    ownership = snapshot["ownership"]
    units = snapshot["collections"]["units"]

    units_by_id = {
        unit["id"]: unit
        for unit in units
        if isinstance(unit.get("id"), str)
    }
    provided_contracts = {
        unit_id: _as_string_list(unit.get("provides"))
        for unit_id, unit in units_by_id.items()
    }

    planned_unit_ids = _resolve_planned_units(units_by_id, target_units)

    jobs = [
        {
            "depends_on": [],
            "job_id": "compile:compiler_owned",
            "kind": "compile",
            "owned_files": sorted(_as_string_list(ownership.get("compiler_files"))),
        }
    ]

    for unit_id in planned_unit_ids:
        unit = units_by_id[unit_id]

        requires_units = sorted(_as_string_list(unit.get("requires")))
        required_contracts = sorted(
            {
                contract_id
                for dependency_id in requires_units
                for contract_id in provided_contracts.get(dependency_id, [])
            }
        )
        depends_on = ["compile:compiler_owned"]
        depends_on.extend(
            f"unit:{dependency_id}"
            for dependency_id in requires_units
            if units_by_id.get(dependency_id, {}).get("generation_mode") == "managed"
        )

        jobs.append(
            {
                "depends_on": depends_on,
                "job_id": f"unit:{unit_id}",
                "kind": "implement_unit",
                "owned_files": sorted(_as_string_list(unit.get("files"))),
                "provided_contracts": sorted(_as_string_list(unit.get("provides"))),
                "required_contracts": required_contracts,
                "required_units": requires_units,
                "tests": sorted(_as_string_list(unit.get("tests"))),
                "unit_id": unit_id,
                "unit_kind": unit.get("kind"),
            }
        )

    return {
        "jobs": jobs,
        "revision_id": revision.revision_id,
    }


def serialize_plan(plan: Mapping[str, Any]) -> str:
    return json.dumps(plan, indent=2, sort_keys=True) + "\n"


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _resolve_planned_units(
    units_by_id: Mapping[str, Mapping[str, Any]],
    target_units: list[str] | None,
) -> list[str]:
    managed_units = {
        unit_id
        for unit_id, unit in units_by_id.items()
        if unit.get("generation_mode") == "managed"
    }
    if target_units is None:
        return sorted(managed_units)

    invalid_units = sorted(set(target_units).difference(managed_units))
    if invalid_units:
        raise ValueError(
            "target units must refer to managed units: " + ", ".join(invalid_units)
        )

    planned: set[str] = set()
    queue = sorted(set(target_units))
    while queue:
        unit_id = queue.pop(0)
        if unit_id in planned:
            continue
        planned.add(unit_id)
        for dependency_id in _as_string_list(units_by_id[unit_id].get("requires")):
            if dependency_id in managed_units and dependency_id not in planned:
                queue.append(dependency_id)

    return sorted(planned)
