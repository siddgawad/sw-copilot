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

from typing import Any

from build123d import BuildSketch, Circle, Locations, Plane, extrude

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

        TODO(claude/codex): implement.
        """
        raise NotImplementedError("HoleWizardHandler._top_face_plane")

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

        TODO(claude/codex): implement.
            from standards.dimension_resolver import resolve_clearance_hole, ...
        """
        raise NotImplementedError("HoleWizardHandler._resolve_dimensions")

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

        TODO(claude/codex): implement.
        """
        raise NotImplementedError("HoleWizardHandler._cut_holes")
