"""Shape-primitive handlers — create_part, create_sketch, rectangle, circle,
extrude_boss, extrude_cut.

These are the load-bearing handlers. Every deterministic pattern emits at
minimum: create_part → create_sketch → add_center_rectangle (or add_circles)
→ extrude_boss. If any of these are wrong, every test in the harness will
fail.

We use build123d's imperative API (`extrude(sketch, amount=N)`) rather
than the BuildPart context manager so each handler can stand alone and
plane information is preserved across handler boundaries.
"""
from __future__ import annotations

from typing import Any

from build123d import (
    BuildSketch,
    Circle,
    Locations,
    Rectangle,
    extrude,
)

from ..context import ExecutionContext, _SketchRecord
from ..plane_mapper import resolve_plane
from .base import OpHandler


# ── create_part ───────────────────────────────────────────────────────────────

class CreatePartHandler(OpHandler):
    """Initialise an empty Part container.

    We don't materialise any geometry yet — the first extrude_boss does that.
    Storing None here just marks the active part id so later handlers know
    where to write.
    """
    op_type = "create_part"

    def execute(self, op: Any, ctx: ExecutionContext) -> None:
        ctx.parts[op.id] = None
        ctx.active_part_id = op.id
        ctx.features[op.id] = "create_part"


# ── create_sketch ─────────────────────────────────────────────────────────────

class CreateSketchHandler(OpHandler):
    """Record the sketch plane so the next geometry handler can build on it.

    The actual sketch geometry is built by add_center_rectangle / add_circles.
    We index the plane by both the op id and the declared sketch_id so
    extrude_boss can reference either.
    """
    op_type = "create_sketch"

    def execute(self, op: Any, ctx: ExecutionContext) -> None:
        plane = resolve_plane(op.plane)
        ctx.extras[f"sketch_plane:{op.sketch_id}"] = plane
        ctx.extras[f"sketch_plane:{op.id}"] = plane
        ctx.features[op.id] = "create_sketch"


# ── add_center_rectangle ──────────────────────────────────────────────────────

class AddCenterRectangleHandler(OpHandler):
    """Build a rectangle centred at (0,0) on the recorded sketch plane.

    `op.center` is currently ignored — build123d's Rectangle is centre-mode
    by default and all our deterministic patterns place rectangles at the
    origin. If centre offset becomes a requirement, wrap Rectangle in
    `with Locations((op.center[0], op.center[1])):`.
    """
    op_type = "add_center_rectangle"

    def execute(self, op: Any, ctx: ExecutionContext) -> None:
        plane = ctx.extras.get(f"sketch_plane:{op.sketch_id}")
        if plane is None:
            raise RuntimeError(
                f"add_center_rectangle references unknown sketch_id={op.sketch_id!r}"
            )
        with BuildSketch(plane) as sk:
            Rectangle(op.length, op.width)
        ctx.pending_sketch = sk.sketch
        ctx.pending_sketch_plane = plane
        ctx.sketch_records.append(
            _SketchRecord(name=op.sketch_id, plane_name=str(plane), entity_count=4)
        )
        ctx.features[op.id] = "rectangle"


# ── add_circles ───────────────────────────────────────────────────────────────

class AddCirclesHandler(OpHandler):
    """Build N circles on the recorded sketch plane.

    Each circle is placed at its declared centre and given its declared
    radius (op.circles[i].diameter / 2). Used for bolt-circle patterns and
    hole-cut sketches.
    """
    op_type = "add_circles"

    def execute(self, op: Any, ctx: ExecutionContext) -> None:
        plane = ctx.extras.get(f"sketch_plane:{op.sketch_id}")
        if plane is None:
            raise RuntimeError(
                f"add_circles references unknown sketch_id={op.sketch_id!r}"
            )
        with BuildSketch(plane) as sk:
            for c in op.circles:
                with Locations((c.center[0], c.center[1])):
                    Circle(c.diameter / 2.0)
        ctx.pending_sketch = sk.sketch
        ctx.pending_sketch_plane = plane
        ctx.sketch_records.append(
            _SketchRecord(name=op.sketch_id, plane_name=str(plane),
                          entity_count=len(op.circles))
        )
        ctx.features[op.id] = "circles"


# ── extrude_boss ──────────────────────────────────────────────────────────────

class ExtrudeBossHandler(OpHandler):
    """Extrude the pending sketch into a solid and fuse with the active part.

    First extrude on an empty part creates the body. Subsequent extrudes
    fuse with what exists, matching SolidWorks's "Boss-Extrude2" behaviour.
    """
    op_type = "extrude_boss"

    def execute(self, op: Any, ctx: ExecutionContext) -> None:
        sketch, _plane = ctx.take_sketch()
        new_solid = extrude(sketch, amount=op.depth_mm)

        active_id = ctx.active_part_id
        if active_id is None:
            # No prior create_part — synthesise one.
            active_id = op.id
            ctx.active_part_id = active_id

        existing = ctx.parts.get(active_id)
        if existing is None:
            ctx.parts[active_id] = new_solid
        else:
            ctx.parts[active_id] = existing + new_solid

        ctx.features[op.id] = "boss"


# ── extrude_cut ───────────────────────────────────────────────────────────────

class ExtrudeCutHandler(OpHandler):
    """Subtract the pending sketch extrusion from the active Part.

    For `through_all=True` we extrude symmetric around the sketch plane
    using `both=True` so the cut clears the body regardless of which side
    the material lies on. For finite cuts we use the requested depth in
    the sketch-plane-normal direction.
    """
    op_type = "extrude_cut"

    def execute(self, op: Any, ctx: ExecutionContext) -> None:
        sketch, _plane = ctx.take_sketch()
        existing = ctx.active_part()
        if existing is None:
            raise RuntimeError("extrude_cut requires an existing part — none active.")

        if op.through_all or op.depth_mm <= 0:
            bb = existing.bounding_box()
            depth = max(bb.size.X, bb.size.Y, bb.size.Z) + 10.0
            tool = extrude(sketch, amount=depth, both=True)
        else:
            tool = extrude(sketch, amount=op.depth_mm)

        ctx.parts[ctx.active_part_id] = existing - tool
        ctx.features[op.id] = "cut"
