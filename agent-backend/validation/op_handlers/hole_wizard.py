"""hole_wizard handler — simple / counterbore / countersink / tapped holes.

STATUS: stubbed. Implementation is delegated. See each function's docstring
for the contract. Implement one function at a time, run the matching test,
commit. Do not change function signatures — other handlers and tests
depend on them.

The corresponding test file is tests/validation/test_hole_wizard.py.

ISO standards used (already implemented, just call them):
    from standards.dimension_resolver import (
        resolve_clearance_hole,        # ISO 273 → {diameter_mm: float}
        resolve_counterbore,           # ISO 4762 → {counterbore_diameter_mm, counterbore_depth_mm, clearance_diameter_mm}
        resolve_countersink,           # ISO 7046  → {csk_diameter_mm, csk_angle_deg}
    )

Coordinate convention:
    Hole positions are in the sketch-local (x_mm, y_mm) frame of the
    "active top face" — i.e. the +Z face of a part extruded from
    Front Plane. resolve_active_top_plane() returns the Plane that
    matches that face. See plane_mapper.py.

WHY this handler is harder than fillet/chamfer:
    Counterbores are a two-step cut (pocket then clearance through-hole).
    Through-holes need a depth large enough to clear the entire part bbox.
    Tapped holes are validated as their clearance equivalent (build123d
    has no concept of threads — they're cosmetic).
"""
from __future__ import annotations

import math
from typing import Any

from build123d import BuildSketch, Circle, Locations, Plane, extrude

from standards.dimension_resolver import (
    resolve_clearance_hole,
    resolve_counterbore,
)
from ..context import ExecutionContext
from .base import OpHandler


# ── Public class ──────────────────────────────────────────────────────────────

class HoleWizardHandler(OpHandler):
    """Cut N holes through (or into) the active part's top face.

    Dispatches on op.hole_type:
        "simple"      → single through-cut with clearance diameter
        "counterbore" → counterbore pocket + clearance through-hole
        "countersink" → countersunk pocket + clearance through-hole
        "tapped"      → same as simple (threads are cosmetic)
    """
    op_type = "hole_wizard"

    def execute(self, op: Any, ctx: ExecutionContext) -> None:
        part = self._active_part(ctx)
        plane = self._top_face_plane(part)
        dims = self._resolve_dimensions(op.fastener_size, op.hole_type)
        self._cut_holes(ctx, plane, op, dims, part)
        ctx.features[op.id] = "hole"

    # ── helpers — IMPLEMENT EACH ONE BELOW ────────────────────────────────────

    def _active_part(self, ctx: ExecutionContext) -> Any:
        """Return the active build123d Part.

        Raises
        ------
        RuntimeError
            If no part exists. hole_wizard cannot create one.
        """
        return ctx.active_part()

    def _top_face_plane(self, part: Any) -> Plane:
        """Return the build123d Plane that lies on the part's top face.

        The "top face" is the +Z face for a part built on Front Plane
        (the convention enforced by rule 26 of the LLM system prompt).
        We use the part's bbox z_max as the plane offset.

        Implementation hint
        -------------------
            bb = part.bounding_box()
            return Plane(origin=(0, 0, bb.max.Z), x_dir=(1,0,0), z_dir=(0,0,1))

        Edge case
        ---------
            If the part was built on Top Plane (Y is thickness), the
            "top" face is at +Y. Detect by comparing bb.size.X/Y/Z —
            the thinnest is the extrude direction; the top face is at
            that axis's max. Mirror the build123d examples in
            CADBooster.SolidDna's SelectTopFaceOfBody (which does the
            same trick on the C# side).

        """
        bb = part.bounding_box()
        dx = abs(bb.size.X)
        dy = abs(bb.size.Y)
        dz = abs(bb.size.Z)

        if dz <= dx and dz <= dy:
            return Plane(origin=(0, 0, bb.max.Z), x_dir=(1, 0, 0), z_dir=(0, 0, 1))
        if dy <= dx and dy <= dz:
            return Plane(origin=(0, bb.max.Y, 0), x_dir=(1, 0, 0), z_dir=(0, 1, 0))
        return Plane(origin=(bb.max.X, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0))

    def _resolve_dimensions(self, fastener_size: str, hole_type: str) -> dict[str, float]:
        """Look up hole dimensions from the standards module.

        Parameters
        ----------
        fastener_size
            e.g. "M6". Pydantic has already coerced casing.
        hole_type
            "simple" | "counterbore" | "countersink" | "tapped"

        Returns
        -------
        dict with these keys (some may be 0.0 depending on hole_type):
            clearance_diameter_mm   — always present
            counterbore_diameter_mm — only for "counterbore"
            counterbore_depth_mm    — only for "counterbore"
            csk_diameter_mm         — only for "countersink"
            csk_angle_deg           — only for "countersink"

        Raises
        ------
        ValueError
            If fastener_size is not in the ISO table.

        """
        clearance = resolve_clearance_hole(fastener_size)
        if clearance is None:
            raise ValueError(f"Unsupported fastener size for clearance hole: {fastener_size}")

        result: dict[str, float] = {
            "clearance_diameter_mm": float(clearance["diameter_mm"]),
            "counterbore_diameter_mm": 0.0,
            "counterbore_depth_mm": 0.0,
            "csk_diameter_mm": 0.0,
            "csk_angle_deg": 90.0,
        }

        if hole_type == "counterbore":
            counterbore = resolve_counterbore(fastener_size)
            if counterbore is None:
                raise ValueError(f"Unsupported fastener size for counterbore: {fastener_size}")
            result["counterbore_diameter_mm"] = float(counterbore["counterbore_diameter_mm"])
            result["counterbore_depth_mm"] = float(counterbore["counterbore_depth_mm"])
        elif hole_type == "countersink":
            counterbore = resolve_counterbore(fastener_size)
            if counterbore is None:
                raise ValueError(f"Unsupported fastener size for countersink: {fastener_size}")
            result["csk_diameter_mm"] = float(counterbore["countersink_diameter_mm"])
            result["csk_angle_deg"] = 90.0

        return result

    def _cut_holes(self, ctx: ExecutionContext, plane: Plane,
                   op: Any, dims: dict[str, float], part: Any) -> None:
        """Perform the through-cut(s) and update ctx.parts.

        Dispatch on op.hole_type. Each branch:
            1. Builds a sketch on `plane` with N circles at op.positions
            2. Extrudes through the part as a cut (use `both=True` for safety)
            3. For counterbore/countersink: additionally cuts a finite-depth
               pocket from the +face into the part by `counterbore_depth_mm`.
            4. Assigns the result to ctx.parts[ctx.active_part_id].

        Helper functions you'll want:
            self._cut_through(part, plane, positions, dia_mm)  → new_part
            self._cut_pocket(part, plane, positions, dia_mm, depth_mm) → new_part

        """
        positions = [(float(p.x_mm), float(p.y_mm)) for p in op.positions]
        clearance_dia = dims["clearance_diameter_mm"]
        self._validate_positions(part, plane, positions, clearance_dia)

        new_part = part
        hole_type = (op.hole_type or "simple").lower()

        if hole_type == "counterbore":
            cbore_dia = dims["counterbore_diameter_mm"]
            cbore_depth = dims["counterbore_depth_mm"]
            self._guard_depth(new_part, cbore_depth, "counterbore")
            self._validate_positions(new_part, plane, positions, cbore_dia)
            new_part = self._cut_pocket(new_part, plane, positions, cbore_dia, cbore_depth)
        elif hole_type == "countersink":
            csk_dia = dims["csk_diameter_mm"]
            angle = math.radians(dims.get("csk_angle_deg", 90.0) / 2.0)
            csk_depth = ((csk_dia - clearance_dia) / 2.0) / max(math.tan(angle), 1e-6)
            self._guard_depth(new_part, csk_depth, "countersink")
            self._validate_positions(new_part, plane, positions, csk_dia)
            new_part = self._cut_pocket(new_part, plane, positions, csk_dia, csk_depth)

        new_part = self._cut_through(new_part, plane, positions, clearance_dia)

        if ctx.active_part_id is None:
            ctx.active_part_id = op.id
        ctx.parts[ctx.active_part_id] = new_part
        ctx.extras[f"hole_dia:{op.id}"] = clearance_dia
        ctx.extras[f"hole_positions:{op.id}"] = positions

    def _cut_through(
        self,
        part: Any,
        plane: Plane,
        positions: list[tuple[float, float]],
        diameter_mm: float,
    ) -> Any:
        """Subtract through-cylinders at all local sketch positions."""
        bb = part.bounding_box()
        depth = max(bb.size.X, bb.size.Y, bb.size.Z) + 10.0
        tool = self._cylindrical_tool(plane, positions, diameter_mm, depth, both=True)
        return part - tool

    def _cut_pocket(
        self,
        part: Any,
        plane: Plane,
        positions: list[tuple[float, float]],
        diameter_mm: float,
        depth_mm: float,
    ) -> Any:
        """Subtract finite-depth pockets inward from the selected top face."""
        tool = self._cylindrical_tool(plane, positions, diameter_mm, -depth_mm, both=False)
        return part - tool

    def _cylindrical_tool(
        self,
        plane: Plane,
        positions: list[tuple[float, float]],
        diameter_mm: float,
        amount_mm: float,
        *,
        both: bool,
    ) -> Any:
        with BuildSketch(plane) as sketch:
            for x_mm, y_mm in positions:
                with Locations((x_mm, y_mm)):
                    Circle(diameter_mm / 2.0)
        return extrude(sketch.sketch, amount=amount_mm, both=both)

    def _guard_depth(self, part: Any, depth_mm: float, label: str) -> None:
        """Reject blind pockets deeper than or equal to the thinnest body axis."""
        bb = part.bounding_box()
        thickness = min(abs(bb.size.X), abs(bb.size.Y), abs(bb.size.Z))
        if depth_mm >= thickness - 0.01:
            raise ValueError(
                f"{label} depth {depth_mm:g} mm exceeds part thickness {thickness:g} mm"
            )

    def _validate_positions(
        self,
        part: Any,
        plane: Plane,
        positions: list[tuple[float, float]],
        diameter_mm: float,
    ) -> None:
        """Reject holes whose projected circles do not fit inside the top face."""
        bb = part.bounding_box()
        radius = diameter_mm / 2.0

        normal = plane.z_dir
        if abs(normal.Z) >= abs(normal.X) and abs(normal.Z) >= abs(normal.Y):
            x_min, x_max = bb.min.X, bb.max.X
            y_min, y_max = bb.min.Y, bb.max.Y
        elif abs(normal.Y) >= abs(normal.X) and abs(normal.Y) >= abs(normal.Z):
            x_min, x_max = bb.min.X, bb.max.X
            y_min, y_max = bb.min.Z, bb.max.Z
        else:
            x_min, x_max = bb.min.Y, bb.max.Y
            y_min, y_max = bb.min.Z, bb.max.Z

        for index, (x_mm, y_mm) in enumerate(positions, start=1):
            if (
                x_mm - radius < x_min - 0.01
                or x_mm + radius > x_max + 0.01
                or y_mm - radius < y_min - 0.01
                or y_mm + radius > y_max + 0.01
            ):
                raise ValueError(
                    f"hole position {index} at ({x_mm:g}, {y_mm:g}) mm with "
                    f"{diameter_mm:g} mm diameter does not fit inside face bounds"
                )
