"""Command-line entrypoints for the blueprint backend."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from blueprint.compiler import CompileError, compile_ir
from blueprint.ir.validator import validate_ir
from blueprint.planner import (
    plan_jobs,
    prepare_job_worktree,
    write_execution_result,
    write_job_manifests,
)
from blueprint.revisions import RevisionValidationError, create_revision
from blueprint.verifier import verify_execution_result, verify_job, verify_repo


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="blueprint")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser(
        "validate-ir",
        help="Validate the .arch canonical model in a repository.",
    )
    validate_parser.add_argument(
        "repo",
        nargs="?",
        default=".",
        help="Path to the repository root. Defaults to the current directory.",
    )

    revision_parser = subparsers.add_parser(
        "create-revision",
        help="Create a canonical revision hash from the .arch model.",
    )
    revision_parser.add_argument(
        "repo",
        nargs="?",
        default=".",
        help="Path to the repository root. Defaults to the current directory.",
    )

    compile_parser = subparsers.add_parser(
        "compile",
        help="Emit deterministic compiler-owned files from the .arch model.",
    )
    compile_parser.add_argument(
        "repo",
        nargs="?",
        default=".",
        help="Path to the repository root. Defaults to the current directory.",
    )

    plan_parser = subparsers.add_parser(
        "plan-jobs",
        help="Build a deterministic full job plan from the .arch model.",
    )
    plan_parser.add_argument(
        "repo",
        nargs="?",
        default=".",
        help="Path to the repository root. Defaults to the current directory.",
    )
    plan_parser.add_argument(
        "--unit",
        action="append",
        dest="units",
        default=None,
        help="Managed unit ID to plan. Repeat to plan more than one unit.",
    )

    verify_parser = subparsers.add_parser(
        "verify",
        help="Verify generated files and managed Python sources against the IR.",
    )
    verify_parser.add_argument(
        "repo",
        nargs="?",
        default=".",
        help="Path to the repository root. Defaults to the current directory.",
    )

    manifests_parser = subparsers.add_parser(
        "write-job-manifests",
        help="Write deterministic job manifest files under .arch/manifests/jobs.",
    )
    manifests_parser.add_argument(
        "repo",
        nargs="?",
        default=".",
        help="Path to the repository root. Defaults to the current directory.",
    )
    manifests_parser.add_argument(
        "--unit",
        action="append",
        dest="units",
        default=None,
        help="Managed unit ID to plan. Repeat to plan more than one unit.",
    )

    verify_job_parser = subparsers.add_parser(
        "verify-job",
        help="Verify one planned job manifest against the current repo state.",
    )
    verify_job_parser.add_argument(
        "manifest",
        help="Path to a planned job manifest file.",
    )
    verify_job_parser.add_argument(
        "--repo",
        default=".",
        help="Path to the repository root. Defaults to the current directory.",
    )
    verify_job_parser.add_argument(
        "--changed-file",
        action="append",
        dest="changed_files",
        default=None,
        help="Relative file path claimed by the job execution. Repeat to provide more than one.",
    )

    verify_result_parser = subparsers.add_parser(
        "verify-execution-result",
        help="Verify one execution result artifact against the current repo state.",
    )
    verify_result_parser.add_argument(
        "result",
        help="Path to an execution result JSON file.",
    )
    verify_result_parser.add_argument(
        "--repo",
        default=".",
        help="Path to the repository root. Defaults to the current directory.",
    )

    write_result_parser = subparsers.add_parser(
        "write-execution-result",
        help="Write one execution result artifact under .arch/manifests/results.",
    )
    write_result_parser.add_argument(
        "manifest",
        help="Path to a planned job manifest file.",
    )
    write_result_parser.add_argument(
        "--repo",
        default=".",
        help="Path to the repository root. Defaults to the current directory.",
    )
    write_result_parser.add_argument(
        "--changed-file",
        action="append",
        dest="changed_files",
        default=None,
        help="Relative file path claimed by the job execution. If omitted, changed files are derived from git diff.",
    )
    write_result_parser.add_argument(
        "--base-ref",
        default="HEAD",
        help="Git base ref used to derive changed files when --changed-file is omitted.",
    )

    worktree_parser = subparsers.add_parser(
        "prepare-job-worktree",
        help="Create a detached worktree for one planned job manifest.",
    )
    worktree_parser.add_argument(
        "manifest",
        help="Path to a planned job manifest file.",
    )
    worktree_parser.add_argument(
        "--repo",
        default=".",
        help="Path to the repository root. Defaults to the current directory.",
    )
    worktree_parser.add_argument(
        "--base-ref",
        default="HEAD",
        help="Git ref used as the worktree base.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "validate-ir":
        report = validate_ir(Path(args.repo))
        if report.ok:
            print("IR validation passed.")
            return 0

        for diagnostic in report.diagnostics:
            print(
                f"{diagnostic.path}: [{diagnostic.code}] {diagnostic.message}",
                file=sys.stderr,
            )
        return 1

    if args.command == "create-revision":
        try:
            revision = create_revision(Path(args.repo))
        except RevisionValidationError as exc:
            for diagnostic in exc.report.diagnostics:
                print(
                    f"{diagnostic.path}: [{diagnostic.code}] {diagnostic.message}",
                    file=sys.stderr,
                )
            return 1

        print(revision.revision_id)
        return 0

    if args.command == "compile":
        try:
            result = compile_ir(Path(args.repo))
        except RevisionValidationError as exc:
            for diagnostic in exc.report.diagnostics:
                print(
                    f"{diagnostic.path}: [{diagnostic.code}] {diagnostic.message}",
                    file=sys.stderr,
                )
            return 1
        except CompileError as exc:
            print(f"[compile.error] {exc}", file=sys.stderr)
            return 1

        for emitted_file in result.emitted_files:
            print(emitted_file)
        return 0

    if args.command == "plan-jobs":
        try:
            plan = plan_jobs(Path(args.repo), target_units=args.units)
        except RevisionValidationError as exc:
            for diagnostic in exc.report.diagnostics:
                print(
                    f"{diagnostic.path}: [{diagnostic.code}] {diagnostic.message}",
                    file=sys.stderr,
                )
            return 1
        except ValueError as exc:
            print(f"[plan.error] {exc}", file=sys.stderr)
            return 1

        print(plan.serialized_plan, end="")
        return 0

    if args.command == "verify":
        report = verify_repo(Path(args.repo))
        if report.ok:
            print("Verification passed.")
            return 0

        for diagnostic in report.diagnostics:
            print(
                f"{diagnostic.path}: [{diagnostic.code}] {diagnostic.message}",
                file=sys.stderr,
            )
        return 1

    if args.command == "write-job-manifests":
        try:
            manifests = write_job_manifests(Path(args.repo), target_units=args.units)
        except RevisionValidationError as exc:
            for diagnostic in exc.report.diagnostics:
                print(
                    f"{diagnostic.path}: [{diagnostic.code}] {diagnostic.message}",
                    file=sys.stderr,
                )
            return 1
        except ValueError as exc:
            print(f"[plan.error] {exc}", file=sys.stderr)
            return 1

        print(manifests.plan_path)
        for manifest_path in manifests.manifest_paths:
            print(manifest_path)
        return 0

    if args.command == "verify-job":
        report = verify_job(
            Path(args.repo),
            Path(args.manifest),
            changed_files=args.changed_files,
        )
        if report.ok:
            print("Job verification passed.")
            return 0

        for diagnostic in report.diagnostics:
            print(
                f"{diagnostic.path}: [{diagnostic.code}] {diagnostic.message}",
                file=sys.stderr,
            )
        return 1

    if args.command == "verify-execution-result":
        report = verify_execution_result(Path(args.repo), Path(args.result))
        if report.ok:
            print("Execution result verification passed.")
            return 0

        for diagnostic in report.diagnostics:
            print(
                f"{diagnostic.path}: [{diagnostic.code}] {diagnostic.message}",
                file=sys.stderr,
            )
        return 1

    if args.command == "write-execution-result":
        try:
            artifact = write_execution_result(
                Path(args.repo),
                Path(args.manifest),
                changed_files=args.changed_files,
                base_ref=args.base_ref,
            )
        except OSError as exc:
            print(f"[execution.error] {exc}", file=sys.stderr)
            return 1
        except ValueError as exc:
            print(f"[execution.error] {exc}", file=sys.stderr)
            return 1

        print(artifact.path)
        return 0

    if args.command == "prepare-job-worktree":
        try:
            worktree = prepare_job_worktree(
                Path(args.repo),
                Path(args.manifest),
                base_ref=args.base_ref,
            )
        except OSError as exc:
            print(f"[worktree.error] {exc}", file=sys.stderr)
            return 1
        except ValueError as exc:
            print(f"[worktree.error] {exc}", file=sys.stderr)
            return 1

        print(worktree.path)
        print(worktree.manifest_path)
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
