"""Deterministic planning from canonical revision snapshots."""

from __future__ import annotations

from dataclasses import dataclass
import json
import shutil
from pathlib import Path
from typing import Any, Dict, Mapping

from blueprint.revisions import Revision, create_revision


@dataclass(frozen=True)
class Plan:
    revision_id: str
    snapshot: Dict[str, Any]
    serialized_plan: str


@dataclass(frozen=True)
class JobManifests:
    revision_id: str
    plan_path: str
    manifest_paths: tuple[str, ...]


@dataclass(frozen=True)
class ExecutionResultArtifact:
    path: str
    changed_files: tuple[str, ...]


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


def write_job_manifests(repo_root: Path, target_units: list[str] | None = None) -> JobManifests:
    repo_root = Path(repo_root).resolve()
    plan = plan_jobs(repo_root, target_units=target_units)
    manifests_root = repo_root / ".arch" / "manifests"
    jobs_root = manifests_root / "jobs"
    if jobs_root.exists():
        shutil.rmtree(jobs_root)
    jobs_root.mkdir(parents=True, exist_ok=True)

    plan_path = manifests_root / "plan.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(plan.serialized_plan, encoding="utf-8")

    manifest_paths: list[str] = []
    for job in plan.snapshot["jobs"]:
        relative_path = job_manifest_path(job["job_id"])
        manifest_path = repo_root / relative_path
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest = build_job_manifest(plan.revision_id, job)
        manifest_path.write_text(serialize_job_manifest(manifest), encoding="utf-8")
        manifest_paths.append(relative_path)

    return JobManifests(
        revision_id=plan.revision_id,
        plan_path=".arch/manifests/plan.json",
        manifest_paths=tuple(sorted(manifest_paths)),
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


def build_job_manifest(revision_id: str, job: Mapping[str, Any]) -> Dict[str, Any]:
    manifest = {"manifest_version": 1, "revision_id": revision_id}
    manifest.update(job)
    return manifest


def build_execution_result(job_manifest: str, changed_files: list[str]) -> Dict[str, Any]:
    return {
        "changed_files": sorted(set(changed_files)),
        "job_manifest": job_manifest,
    }


def serialize_job_manifest(manifest: Mapping[str, Any]) -> str:
    return json.dumps(manifest, indent=2, sort_keys=True) + "\n"


def serialize_execution_result(result: Mapping[str, Any]) -> str:
    return json.dumps(result, indent=2, sort_keys=True) + "\n"


def job_manifest_path(job_id: str) -> str:
    kind, separator, name = job_id.partition(":")
    if not separator or not kind or not name:
        raise ValueError(f"invalid job_id: {job_id}")
    return f".arch/manifests/jobs/{kind}/{name}.json"


def job_result_path(job_id: str) -> str:
    kind, separator, name = job_id.partition(":")
    if not separator or not kind or not name:
        raise ValueError(f"invalid job_id: {job_id}")
    return f".arch/manifests/results/{kind}/{name}.json"


def write_execution_result(
    repo_root: Path,
    manifest_path: Path,
    *,
    changed_files: list[str],
) -> ExecutionResultArtifact:
    repo_root = Path(repo_root).resolve()
    manifest_path = Path(manifest_path)
    if not manifest_path.is_absolute():
        manifest_path = (repo_root / manifest_path).resolve()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    job_id = manifest.get("job_id")
    if not isinstance(job_id, str) or not job_id:
        raise ValueError("job manifest is missing a valid job_id")

    result_path = repo_root / job_result_path(job_id)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    relative_manifest_path = manifest_path.resolve().relative_to(repo_root).as_posix()
    artifact = build_execution_result(
        relative_manifest_path,
        changed_files=changed_files,
    )
    result_path.write_text(serialize_execution_result(artifact), encoding="utf-8")
    return ExecutionResultArtifact(
        path=job_result_path(job_id),
        changed_files=tuple(artifact["changed_files"]),
    )


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
