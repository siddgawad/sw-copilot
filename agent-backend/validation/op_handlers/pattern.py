"""pattern handlers — circular_pattern, linear_pattern, mirror.

STATUS: stubbed. Implementation is delegated.

The corresponding test file is tests/validation/test_pattern.py.

These are the "hardest" handlers because they have to find features by
op_id from prior history and replicate their geometry. For validation,
we approximate: we know what the source feature did (because we
recorded it in ctx.features), so we can re-cut/re-extrude N times at
the pattern locations.

The flange + bolt circle case is the canonical test:
    create_sketch → add_circles[1] @ (PCD/2, 0) → extrude_cut → circular_pattern count=6
"""
from __future__ import annotations

import math
from typing import Any

from build123d import BuildSketch, Circle, Locations, Plane, extrude

from ..context import ExecutionContext
from .base import OpHandler


# ── circular_pattern ──────────────────────────────────────────────────────────

class CircularPatternHandler(OpHandler):
    """Replicate the source hole/cut around a circle of count instances.

    Inputs
    ------
    op.source_ids
        List of op ids whose geometry should be patterned. For validation,
        we assume each source is a hole_wizard or extrude_cut whose
        position is known from the prior add_circles op.
    op.count
        Number of instances total (including the source). count >= 2.
    op.pcd_mm
        Pitch circle diameter — the circle the instances sit on.
    op.axis_feature_id
        Optional. Defaults to the part's Z axis (out of the top face).
    """
    op_type = "circular_pattern"

    def execute(self, op: Any, ctx: ExecutionContext) -> None:
        part = ctx.active_part()
        plane = self._infer_top_plane(part)
        diameter = self._infer_source_diameter(op.source_ids, ctx)
        positions = self._pattern_positions(op.pcd_mm, op.count)
        new_part = self._cut_at_positions(part, plane, positions, diameter)
        ctx.parts[ctx.active_part_id] = new_part
        ctx.features[op.id] = "circular_pattern"

    # ── helpers ───────────────────────────────────────────────────────────

    def _infer_top_plane(self, part: Any) -> Plane:
        """Same as HoleWizardHandler._top_face_plane. Consider extracting
        a shared helper in a new validation/geometry.py if you implement
        both at once."""
        bb = part.bounding_box()
        dx = abs(bb.size.X)
        dy = abs(bb.size.Y)
        dz = abs(bb.size.Z)

        if dz <= dx and dz <= dy:
            return Plane(origin=(0, 0, bb.max.Z), x_dir=(1, 0, 0), z_dir=(0, 0, 1))
        if dy <= dx and dy <= dz:
            return Plane(origin=(0, bb.max.Y, 0), x_dir=(1, 0, 0), z_dir=(0, 1, 0))
        return Plane(origin=(bb.max.X, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0))

    def _infer_source_diameter(self, source_ids: list[str], ctx: ExecutionContext) -> float:
        """Look at ctx.extras for the diameter the source hole used.

        The hole_wizard handler should stash `dims["clearance_diameter_mm"]`
        in ctx.extras[f"hole_dia:{op.id}"] when it cuts. This helper reads it.

        If multiple source_ids and they disagree, take the first.

        """
        for source_id in source_ids:
            diameter = ctx.extras.get(f"hole_dia:{source_id}")
            if diameter is not None:
                return float(diameter)
        raise ValueError(
            f"Could not infer source hole diameter for circular_pattern from {source_ids!r}"
        )

    def _pattern_positions(self, pcd_mm: float, count: int) -> list[tuple[float, float]]:
        """Return N (x, y) positions evenly spaced on a circle of radius pcd_mm/2.

        Implementation hint (this one is small, implement inline):
            r = pcd_mm / 2.0
            return [(r * math.cos(2 * math.pi * i / count),
                     r * math.sin(2 * math.pi * i / count))
                    for i in range(count)]

        """
        if count < 2:
            raise ValueError("circular_pattern count must be >= 2")
        if pcd_mm <= 0:
            raise ValueError("circular_pattern pcd_mm must be positive")

        radius = pcd_mm / 2.0
        return [
            (
                radius * math.cos(2.0 * math.pi * i / count),
                radius * math.sin(2.0 * math.pi * i / count),
            )
            for i in range(count)
        ]

    def _cut_at_positions(self, part: Any, plane: Plane,
                          positions: list[tuple[float, float]],
                          diameter: float) -> Any:
        """Cut a through-hole at each (x, y) on `plane` of `diameter`.
        Returns the new part.

        """
        bb = part.bounding_box()
        depth = max(bb.size.X, bb.size.Y, bb.size.Z) + 10.0
        with BuildSketch(plane) as sketch:
            for x_mm, y_mm in positions:
                with Locations((x_mm, y_mm)):
                    Circle(diameter / 2.0)
        tool = extrude(sketch.sketch, amount=depth, both=True)
        return part - tool


# ── linear_pattern ────────────────────────────────────────────────────────────

class LinearPatternHandler(OpHandler):
    """Replicate the source along one or two axes.

    Inputs
    ------
    op.source_ids
        List of op ids whose geometry should be patterned.
    op.dir1_count, op.dir1_spacing_mm
        Count and spacing along the first axis (default X).
    op.dir2_count, op.dir2_spacing_mm
        Count and spacing along the second axis (default Y).
    """
    op_type = "linear_pattern"

    def execute(self, op: Any, ctx: ExecutionContext) -> None:
        # Same dispatch pattern as CircularPatternHandler:
        # 1. infer top plane
        # 2. infer source diameter from ctx.extras
        # 3. compute grid positions
        # 4. cut at each position
        raise NotImplementedError("LinearPatternHandler.execute")


# ── mirror ────────────────────────────────────────────────────────────────────

class MirrorHandler(OpHandler):
    """Reflect the source feature across a plane.

    Inputs
    ------
    op.source_ids
        List of op ids whose geometry to mirror.
    op.mirror_plane
        "Front Plane" | "Top Plane" | "Right Plane". Default "Right Plane".
    """
    op_type = "mirror"

    def execute(self, op: Any, ctx: ExecutionContext) -> None:
        # In build123d, mirror() reflects a Compound. The simplest validation:
        # 1. Take the active part
        # 2. Apply build123d's mirror(part, plane) where plane is from plane_mapper
        # 3. Fuse mirror+original
        # This loses fidelity for partial mirrors but matches the bbox.
        raise NotImplementedError("MirrorHandler.execute")
