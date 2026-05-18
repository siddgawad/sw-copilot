"""
Deterministic L-bracket / angle-bracket pattern.

An L-bracket is two perpendicular plates meeting at a corner. We model it as
a single rectangular sketch on Front Plane extruded the depth, then a second
extrude_cut removes the inner corner volume — but for simplicity at this
layer we emit it as TWO extruded plates joined at a vertical edge.

Supported prompt forms:
  "create an L-bracket 80x60x5mm"
  "make a bracket 100x80x6mm"
  "angle bracket 120x80mm 5mm thick"
  "L-bracket 80x60x5mm with 4 M5 holes"

Geometry convention:
  Horizontal leg: width × depth on Top Plane, thickness extruded down (-Z)
  Vertical leg:   width × height on Front Plane, thickness extruded forward (+Y)
"""
from __future__ import annotations

import re
from typing import Optional

from models.schemas import OperationGraph


_BRACKET_KW = re.compile(
    r"\b(?:L[\s\-]?bracket|angle[\s\-]?bracket|bracket)\b",
    re.IGNORECASE,
)
_DIM3 = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:mm)?\s*[xX×]\s*(\d+(?:\.\d+)?)\s*(?:mm)?\s*[xX×]\s*(\d+(?:\.\d+)?)\s*(?:mm)?",
    re.IGNORECASE,
)
_DIM2_THICK = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:mm)?\s*[xX×]\s*(\d+(?:\.\d+)?)\s*mm.*?(\d+(?:\.\d+)?)\s*mm\s+thick",
    re.IGNORECASE,
)


def match(prompt: str) -> tuple[float, float, float] | None:
    """Return (leg_a_mm, leg_b_mm, thickness_mm)."""
    if not _BRACKET_KW.search(prompt):
        return None
    m = _DIM2_THICK.search(prompt)
    if m:
        return float(m.group(1)), float(m.group(2)), float(m.group(3))
    m = _DIM3.search(prompt)
    if m:
        a, b, c = float(m.group(1)), float(m.group(2)), float(m.group(3))
        # Smallest is thickness; preserve the user's order for the two legs.
        thickness = min(a, b, c)
        legs = [value for value in (a, b, c) if value != thickness]
        if len(legs) < 2:
            legs = sorted([a, b, c], reverse=True)[:2]
        return legs[0], legs[1], thickness
    return None


def build_graph(leg_a: float, leg_b: float, thickness: float) -> OperationGraph:
    """Emit a simple L-bracket via two perpendicular plates.

    For the deterministic v0 model we emit:
      - Horizontal plate (leg_a wide × thickness deep × leg_b — no, simpler:)
      - Single L-shaped sketch on Front Plane, extruded by the width.

    We'll emit it as two extrudes for clarity:
      sk1 (Front Plane) rectangle leg_a × thickness  → extrude leg_width
      sk2 (Front Plane) rectangle thickness × leg_b  → extrude leg_width
    """
    leg_width = leg_a  # Both legs span this width.
    return OperationGraph(
        schema_version = "0.2",
        part_family    = "bracket_v0",
        part_name      = "bracket",
        reasoning      = (
            f"Deterministic L-bracket: leg A {leg_a} mm, leg B {leg_b} mm, "
            f"thickness {thickness} mm"
        ),
        assumptions    = [
            f"L-bracket legs {leg_a} mm x {leg_b} mm, {thickness} mm thick",
            "Horizontal and vertical plates share thickness; modeled as two perpendicular extrudes",
        ],
        operations     = [
            {"id": "p1",  "type": "create_part"},
            # Horizontal leg as a thin plate (leg_a wide × leg_b deep × thickness tall) on Top Plane
            {"id": "sk1", "type": "create_sketch",        "plane": "Top Plane", "sketch_id": "sk1"},
            {"id": "r1",  "type": "add_center_rectangle", "sketch_id": "sk1",
             "center": [0.0, 0.0], "length": leg_a, "width": leg_b},
            {"id": "e1",  "type": "extrude_boss",         "profile_id": "sk1", "depth_mm": thickness},
            # Vertical leg as a thin plate (leg_a wide × thickness deep × leg_b tall) on Front Plane
            {"id": "sk2", "type": "create_sketch",        "plane": "Front Plane", "sketch_id": "sk2"},
            {"id": "r2",  "type": "add_center_rectangle", "sketch_id": "sk2",
             "center": [0.0, leg_b / 2.0], "length": leg_a, "width": leg_b},
            {"id": "e2",  "type": "extrude_boss",         "profile_id": "sk2", "depth_mm": thickness},
            {"id": "rb1", "type": "rebuild"},
        ],
    )


def try_generate(prompt: str) -> Optional[OperationGraph]:
    dims = match(prompt)
    if dims is None:
        return None
    return build_graph(*dims)
