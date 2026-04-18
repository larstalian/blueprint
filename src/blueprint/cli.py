"""Command-line entrypoints for the blueprint backend."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from blueprint.ir.validator import validate_ir
from blueprint.revisions import RevisionValidationError, create_revision


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

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
