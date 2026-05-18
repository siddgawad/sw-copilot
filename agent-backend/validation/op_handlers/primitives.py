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

import math

from build123d import (
    BuildLine,
    BuildSketch,
    CenterArc,
    Circle,
    Ellipse,
    Line,
    Locations,
    Plane,
    Polyline,
    Rectangle,
    RegularPolygon,
    Spline,
    extrude,
    make_face,
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


class SketchHandler(OpHandler):
    """Build legacy generic sketch operations from their entity list."""
    op_type = "sketch"

    def execute(self, op: Any, ctx: ExecutionContext) -> None:
        plane = _resolve_sketch_plane(op.plane, ctx)
        entity_count = 0
        with BuildSketch(plane) as sk:
            for entity in op.entities:
                if entity.type == "circle":
                    with Locations((entity.cx_mm, entity.cy_mm)):
                        Circle(entity.radius_mm)
                    entity_count += 1
                elif entity.type == "rectangle":
                    cx = (entity.x1_mm + entity.x2_mm) / 2.0
                    cy = (entity.y1_mm + entity.y2_mm) / 2.0
                    length = abs(entity.x2_mm - entity.x1_mm)
                    width = abs(entity.y2_mm - entity.y1_mm)
                    with Locations((cx, cy)):
                        Rectangle(length, width)
                    entity_count += 4
                elif entity.type == "line":
                    Line((entity.x1_mm, entity.y1_mm), (entity.x2_mm, entity.y2_mm))
                    entity_count += 1
                elif entity.type == "arc":
                    # build123d CenterArc: arc by centre + radius + start angle + arc angle
                    arc_angle = entity.end_angle_deg - entity.start_angle_deg
                    if entity.clockwise:
                        arc_angle = -abs(arc_angle)
                    with Locations((entity.cx_mm, entity.cy_mm)):
                        CenterArc(
                            radius=entity.radius_mm,
                            start_angle=entity.start_angle_deg,
                            arc_size=arc_angle,
                        )
                    entity_count += 1
                elif entity.type == "ellipse":
                    with Locations((entity.cx_mm, entity.cy_mm)):
                        Ellipse(
                            x_radius=entity.semi_major_mm,
                            y_radius=entity.semi_minor_mm,
                            rotation=entity.rotation_deg,
                        )
                    entity_count += 1
                elif entity.type == "polygon":
                    with Locations((entity.cx_mm, entity.cy_mm)):
                        RegularPolygon(
                            radius=entity.radius_mm,
                            side_count=entity.sides,
                            rotation=entity.rotation_deg,
                        )
                    entity_count += entity.sides
                elif entity.type == "spline":
                    pts = [tuple(p) for p in entity.points]
                    if entity.closed and len(pts) >= 3 and pts[0] != pts[-1]:
                        pts.append(pts[0])
                    # Splines are 1D curves; build them in a BuildLine context
                    # and convert to a face for sketch use.
                    with BuildLine() as _spline_ln:
                        Spline(*pts)
                    if entity.closed:
                        make_face()
                    entity_count += 1
                else:
                    raise ValueError(f"Unsupported sketch entity type: {entity.type!r}")

        ctx.pending_sketch = sk.sketch
        ctx.pending_sketch_plane = plane
        ctx.sketch_records.append(
            _SketchRecord(name=op.id, plane_name=str(plane), entity_count=entity_count)
        )
        ctx.features[op.id] = "sketch"


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
            with Locations((op.center[0], op.center[1])):
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
        ctx.extras["pending_circles"] = [
            {
                "center": (float(c.center[0]), float(c.center[1])),
                "diameter": float(c.diameter),
            }
            for c in op.circles
        ]
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
        pending_circles = ctx.extras.pop("pending_circles", None)
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
        if pending_circles:
            ctx.extras[f"hole_dia:{op.id}"] = float(pending_circles[0]["diameter"])
            ctx.extras[f"hole_positions:{op.id}"] = [
                tuple(c["center"]) for c in pending_circles
            ]


def _resolve_sketch_plane(plane_name: str | None, ctx: ExecutionContext):
    """Resolve standard planes plus '<feature> top' aliases for validation."""
    if plane_name and plane_name.strip().lower().endswith(" top"):
        part = ctx.active_part()
        bb = part.bounding_box()
        dx = abs(bb.size.X)
        dy = abs(bb.size.Y)
        dz = abs(bb.size.Z)
        from build123d import Plane

        if dz <= dx and dz <= dy:
            return Plane(origin=(0, 0, bb.max.Z), x_dir=(1, 0, 0), z_dir=(0, 0, 1))
        if dy <= dx and dy <= dz:
            return Plane(origin=(0, bb.max.Y, 0), x_dir=(1, 0, 0), z_dir=(0, 1, 0))
        return Plane(origin=(bb.max.X, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0))

    return resolve_plane(plane_name)
