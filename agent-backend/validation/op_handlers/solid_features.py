"""Solid feature handlers that preserve bbox parity in build123d validation."""
from __future__ import annotations

from typing import Any

from build123d import offset

from ..context import ExecutionContext
from .base import OpHandler


class ShellHandler(OpHandler):
    """Validate shell by offsetting the active solid inward with the top face open."""

    op_type = "shell"

    def execute(self, op: Any, ctx: ExecutionContext) -> None:
        part = ctx.active_part()
        if part is None:
            raise RuntimeError("shell requires an existing solid part")

        thickness = float(getattr(op, "thickness_mm", 0.0) or 0.0)
        if thickness <= 0:
            raise ValueError("shell thickness_mm must be positive")

        bb = part.bounding_box()
        min_axis = min(abs(bb.size.X), abs(bb.size.Y), abs(bb.size.Z))
        if thickness >= min_axis / 2.0:
            raise ValueError(
                f"shell thickness {thickness:g} mm is too large for minimum body "
                f"dimension {min_axis:g} mm"
            )

        faces = list(part.faces())
        if not faces:
            raise ValueError("shell requires a solid with planar faces")

        top_face = max(faces, key=lambda face: face.center().Z)
        ctx.parts[ctx.active_part_id] = offset(part, amount=-thickness, openings=top_face)
        ctx.features[op.id] = "shell"
