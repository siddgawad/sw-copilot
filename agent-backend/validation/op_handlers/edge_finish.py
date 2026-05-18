"""edge_finish handlers — fillet and chamfer.

STATUS: stubbed. Implementation is delegated.

The corresponding test file is tests/validation/test_edge_finish.py.

CRITICAL: SolidWorks cannot fillet the circular rim of a through-hole.
The Python planner already blocks this at the prompt level (see
patterns/followup_features.py). These handlers don't need to re-block —
they just need to refuse to fillet circular edges if encountered (raise
ValueError so the backend records an error rather than a crash).
"""
from __future__ import annotations

from typing import Any, Iterable

from build123d import Edge, GeomType

from ..context import ExecutionContext
from .base import OpHandler


# ── Public classes ────────────────────────────────────────────────────────────

class FilletHandler(OpHandler):
    """Apply a constant-radius fillet to selected edges.

    op.feature_ids semantics:
        []                              → all linear external edges
        ["__top_edges__"] / ["top_edges"] → boundary edges of the top face
        ["<feature_op_id>", ...]        → edges of the named feature(s)
    """
    op_type = "fillet"

    def execute(self, op: Any, ctx: ExecutionContext) -> None:
        from build123d import fillet  # imported lazily to keep top-level light

        part = self._active_part(ctx)
        edges = self._select_edges(part, op.feature_ids, min_length_mm=op.radius_mm * 2.0)
        self._guard_radius(part, op.radius_mm)
        new_part = fillet(edges, radius=op.radius_mm)
        ctx.parts[ctx.active_part_id] = new_part
        ctx.features[op.id] = "fillet"

    # ── helpers ───────────────────────────────────────────────────────────

    def _active_part(self, ctx: ExecutionContext) -> Any:
        return ctx.active_part()

    def _select_edges(self, part: Any, feature_ids: list[str], min_length_mm: float) -> "list[Edge]":
        """Return the edges to fillet for this part + selector.

        Filter rules (match the C# executor's SelectEdgesForFillet):
            * Skip arc/circular edges (GeomType.CIRCLE) — they'd self-intersect
            * Skip edges shorter than `min_length_mm` — they'd fail
            * "__top_edges__" → only edges on the highest-Z face
            * []              → every remaining edge

        Implementation hint
        -------------------
            edges = []
            for e in part.edges():
                if e.geom_type == GeomType.CIRCLE:
                    continue
                if e.length < min_length_mm:
                    continue
                edges.append(e)
            return edges

        For "__top_edges__":
            top_face = max(part.faces(), key=lambda f: f.center().Z)
            return [e for e in top_face.edges() if ...]

        TODO(claude/codex): implement.
        """
        raise NotImplementedError("FilletHandler._select_edges")

    def _guard_radius(self, part: Any, radius_mm: float) -> None:
        """Refuse radii > half the part's thinnest dimension.

        Mirrors the C# executor's pre-check. Raises ValueError on violation.

        TODO(claude/codex): implement.
        """
        raise NotImplementedError("FilletHandler._guard_radius")


class ChamferHandler(OpHandler):
    """Apply a constant-length chamfer to selected edges. Same edge-selector
    semantics as FilletHandler."""
    op_type = "chamfer"

    def execute(self, op: Any, ctx: ExecutionContext) -> None:
        from build123d import chamfer

        part = self._active_part(ctx)
        edges = self._select_edges(part, op.feature_ids, min_length_mm=op.distance_mm * 2.0)
        self._guard_distance(part, op.distance_mm)
        new_part = chamfer(edges, length=op.distance_mm)
        ctx.parts[ctx.active_part_id] = new_part
        ctx.features[op.id] = "chamfer"

    # ── helpers ───────────────────────────────────────────────────────────

    def _active_part(self, ctx: ExecutionContext) -> Any:
        return ctx.active_part()

    def _select_edges(self, part: Any, feature_ids: list[str], min_length_mm: float) -> "list[Edge]":
        """Identical contract to FilletHandler._select_edges. Suggested
        implementation: extract a free function `_select_external_edges`
        in this module and call it from both handlers.

        TODO(claude/codex): implement.
        """
        raise NotImplementedError("ChamferHandler._select_edges")

    def _guard_distance(self, part: Any, distance_mm: float) -> None:
        """Refuse distances > half the part's thinnest dimension.

        TODO(claude/codex): implement.
        """
        raise NotImplementedError("ChamferHandler._guard_distance")
