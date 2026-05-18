"""Handlers for meta operations: rebuild, noop, delete_feature.

These don't produce geometry. They exist so the registry has full coverage
of the OperationGraph schema and the parity test harness doesn't have to
special-case them.
"""
from __future__ import annotations

from typing import Any

from ..context import ExecutionContext
from .base import OpHandler


class RebuildHandler(OpHandler):
    """A 'rebuild' in SolidWorks rebuilds the feature tree. build123d is
    always 'rebuilt' on each operation, so this is a no-op."""
    op_type = "rebuild"

    def execute(self, op: Any, ctx: ExecutionContext) -> None:
        # Register the feature so feature_count reflects it.
        ctx.features[op.id] = "rebuild"


class NoopHandler(OpHandler):
    """A noop carries a message but does not affect geometry."""
    op_type = "noop"

    def execute(self, op: Any, ctx: ExecutionContext) -> None:
        # Record as a feature so feature_count reflects user intent
        # (helpful when diffing against PartReport).
        ctx.features[op.id] = "noop"


class DeleteFeatureHandler(OpHandler):
    """Validation-only: build123d doesn't model 'delete an arbitrary feature'
    from a feature tree (the tree is implicit in the with-block). For
    validation purposes we mark the feature as deleted and move on. The
    real delete happens in C# against SolidWorks.

    If a real geometric delete is needed for validation (e.g. modify-
    thickness flows that delete Boss-Extrude1 then recreate), the LLM
    should emit a new create_sketch + extrude_boss — this handler does
    nothing destructive.
    """
    op_type = "delete_feature"

    def execute(self, op: Any, ctx: ExecutionContext) -> None:
        ctx.features[op.id] = "delete_feature"


class EditFeatureHandler(OpHandler):
    """Validation-only: build123d cannot retroactively modify a previously-
    built feature (parts are immutable in the imperative API). We record the
    intent so feature_count is correct, but the geometric change is verified
    indirectly — the next pattern-parity run should produce the new bbox.

    The real edit happens in C# via Feature.ModifyDefinition2.
    """
    op_type = "edit_feature"

    def execute(self, op: Any, ctx: ExecutionContext) -> None:
        ctx.features[op.id] = "edit_feature"
