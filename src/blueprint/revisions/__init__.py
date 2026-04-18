"""Revision creation for canonical IR snapshots."""

from blueprint.revisions.core import (
    Revision,
    RevisionValidationError,
    create_revision,
    serialize_snapshot,
)

__all__ = [
    "Revision",
    "RevisionValidationError",
    "create_revision",
    "serialize_snapshot",
]

