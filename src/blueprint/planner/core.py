"""Deterministic planning from canonical revision snapshots."""

from __future__ import annotations

from dataclasses import dataclass
import json
import shutil
from pathlib import Path
import subprocess
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


@dataclass(frozen=True)
class JobWorktree:
    path: str
    manifest_path: str
    base_ref: str


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
    changed_files: list[str] | None = None,
    base_ref: str = "HEAD",
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
    if changed_files is None:
        changed_files = _changed_files_from_git(repo_root, base_ref=base_ref)
    artifact = build_execution_result(
        relative_manifest_path,
        changed_files=changed_files,
    )
    result_path.write_text(serialize_execution_result(artifact), encoding="utf-8")
    return ExecutionResultArtifact(
        path=job_result_path(job_id),
        changed_files=tuple(artifact["changed_files"]),
    )


def prepare_job_worktree(
    repo_root: Path,
    manifest_path: Path,
    *,
    base_ref: str = "HEAD",
) -> JobWorktree:
    repo_root = Path(repo_root).resolve()
    manifest_path = Path(manifest_path)
    if not manifest_path.is_absolute():
        manifest_path = (repo_root / manifest_path).resolve()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    job_id = manifest.get("job_id")
    if not isinstance(job_id, str) or not job_id:
        raise ValueError("job manifest is missing a valid job_id")

    worktree_root = _worktree_path(repo_root, job_id)
    if worktree_root.exists():
        raise ValueError(f"worktree already exists: {worktree_root}")

    worktree_root.parent.mkdir(parents=True, exist_ok=True)
    _run_git(repo_root, "worktree", "add", "--detach", str(worktree_root), base_ref)

    relative_manifest_path = manifest_path.resolve().relative_to(repo_root).as_posix()
    target_manifest_path = worktree_root / relative_manifest_path
    target_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(manifest_path, target_manifest_path)

    return JobWorktree(
        path=str(worktree_root),
        manifest_path=str(target_manifest_path),
        base_ref=base_ref,
    )


def remove_job_worktree(
    repo_root: Path,
    worktree_path: Path,
    *,
    force: bool = False,
) -> None:
    repo_root = Path(repo_root).resolve()
    worktree_path = Path(worktree_path).resolve()
    worktrees_root = _worktrees_root(repo_root)
    try:
        worktree_path.relative_to(worktrees_root)
    except ValueError as exc:
        raise ValueError(f"worktree is outside managed root: {worktree_path}") from exc

    _cleanup_worktree_manifests(worktree_path)
    args = ["worktree", "remove"]
    if force:
        args.append("--force")
    args.append(str(worktree_path))
    _run_git(repo_root, *args)
    _remove_empty_parents(worktree_path.parent, stop_at=worktrees_root)


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _changed_files_from_git(repo_root: Path, *, base_ref: str) -> list[str]:
    diff_files = _run_git_lines(
        repo_root,
        "diff",
        "--name-only",
        "--relative",
        base_ref,
        "--",
    )
    untracked_files = _run_git_lines(
        repo_root,
        "ls-files",
        "--others",
        "--exclude-standard",
    )
    return sorted(
        {
            path
            for path in diff_files + untracked_files
            if not path.startswith(".arch/manifests/")
        }
    )


def _run_git_lines(repo_root: Path, *args: str) -> list[str]:
    output = _run_git(repo_root, *args)
    return [line for line in output.splitlines() if line]


def _run_git(repo_root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or exc.stdout.strip() or "git command failed"
        raise ValueError(message) from exc

    return result.stdout


def _worktree_path(repo_root: Path, job_id: str) -> Path:
    kind, separator, name = job_id.partition(":")
    if not separator or not kind or not name:
        raise ValueError(f"invalid job_id: {job_id}")
    return _worktrees_root(repo_root) / kind / name


def _worktrees_root(repo_root: Path) -> Path:
    return repo_root.parent / f".{repo_root.name}-worktrees"


def _remove_empty_parents(path: Path, *, stop_at: Path) -> None:
    current = path
    while current != stop_at and current.exists():
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def _cleanup_worktree_manifests(worktree_path: Path) -> None:
    manifests_root = worktree_path / ".arch" / "manifests"
    if manifests_root.exists():
        shutil.rmtree(manifests_root)


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
