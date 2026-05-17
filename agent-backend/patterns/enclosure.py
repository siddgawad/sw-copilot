"""
Deterministic enclosure pattern — box with a hollow interior (shelled) and
optional corner mounting holes.

This is one of the most common engineering parts: an instrument case, junction
box, or housing. We model it as box -> shell -> corner holes.

Supported prompt forms:
  "create an enclosure 100x60x40mm with 2mm walls"
  "make a housing 200x150x80mm 3mm wall thickness"
  "junction box 80x80x40mm 2mm walls with 4 M3 mounting holes at corners"
  "instrument case 150x100x50mm 2mm walls"
"""
from __future__ import annotations

import re
from typing import Optional

from models.schemas import OperationGraph
from patterns.compound_features import append_compound_features
from standards.dimension_resolver import resolve_clearance_hole


_ENCLOSURE_KW = re.compile(
    r"\b(enclosure|housing|junction\s+box|instrument\s+case|case|chassis|cabinet)\b",
    re.IGNORECASE,
)
_DIMS = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:mm)?\s*[xX×]\s*(\d+(?:\.\d+)?)\s*(?:mm)?\s*[xX×]\s*(\d+(?:\.\d+)?)\s*(?:mm)?",
    re.IGNORECASE,
)
_WALL = re.compile(
    r"(\d+(?:\.\d+)?)\s*mm\s+wall(?:s|\s+thickness)?",
    re.IGNORECASE,
)
_CORNER_HOLES = re.compile(
    r"\b(?:(\d+|four)\s+)?M(\d{1,2})\s+(?:mounting\s+|machine\s+screw\s+)?holes?\s+at\s+(?:the\s+)?corners?",
    re.IGNORECASE,
)


def try_generate(prompt: str) -> Optional[OperationGraph]:
    if not _ENCLOSURE_KW.search(prompt):
        return None
    dim = _DIMS.search(prompt)
    if not dim:
        return None
    a, b, c = float(dim.group(1)), float(dim.group(2)), float(dim.group(3))
    # Largest two are footprint; smallest is height (or use last as height).
    dims = sorted([a, b, c])
    height = dims[0]
    length = max(dims[1], dims[2])
    width  = min(dims[1], dims[2])
    if height < min(length, width) * 0.05:
        # Sanity: ridiculously thin "enclosure" — bail.
        return None

    wall = 2.0
    wm = _WALL.search(prompt)
    if wm:
        wall = float(wm.group(1))

    bolt_count = 0
    bolt_size = "M3"
    hm = _CORNER_HOLES.search(prompt)
    if hm:
        token = (hm.group(1) or "").lower()
        bolt_count = {"four": 4}.get(token, int(token) if token.isdigit() else 4)
        bolt_size = f"M{hm.group(2)}"

    operations: list[dict] = [
        {"id": "p1",  "type": "create_part"},
        {"id": "sk1", "type": "create_sketch",        "plane": "Top Plane", "sketch_id": "sk1"},
        {"id": "r1",  "type": "add_center_rectangle", "sketch_id": "sk1",
         "center": [0.0, 0.0], "length": length, "width": width},
        {"id": "e1",  "type": "extrude_boss",         "profile_id": "sk1", "depth_mm": height},
        # Shell the solid box (remove the top face, keep all other walls).
        {"id": "sh1", "type": "shell",                "face_of": "e1", "thickness_mm": wall},
    ]
    assumptions = [
        f"Enclosure {length:g} x {width:g} x {height:g} mm with {wall:g} mm walls",
        "Top face is the open face; remaining 5 faces become walls",
    ]

    if bolt_count >= 2:
        clearance = resolve_clearance_hole(bolt_size) or {"diameter_mm": 3.4}
        diameter = float(clearance["diameter_mm"])
        inset = max(diameter / 2.0 + 2.0, min(8.0, (min(length, width) - diameter) / 2.0))
        x = length / 2.0 - inset
        y = width / 2.0 - inset
        positions = [
            {"x_mm": -x, "y_mm": -y},
            {"x_mm":  x, "y_mm": -y},
            {"x_mm": -x, "y_mm":  y},
            {"x_mm":  x, "y_mm":  y},
        ][:bolt_count]
        operations.append({
            "id":            "h1",
            "type":          "hole_wizard",
            "face_of":       "e1",
            "hole_type":     "simple",
            "fastener_size": bolt_size,
            "through_all":   True,
            "depth_mm":      0.0,
            "positions":     positions,
        })
        assumptions.append(f"{bolt_count}x {bolt_size} corner mounting holes (clearance dia {diameter:g} mm)")

    operations.append({"id": "rb1", "type": "rebuild"})

    graph = OperationGraph(
        schema_version = "0.2",
        part_family    = "enclosure_v0",
        part_name      = "enclosure",
        reasoning      = (
            f"Enclosure {length} x {width} x {height} mm, {wall} mm walls"
            + (f", {bolt_count}x {bolt_size} mounting holes" if bolt_count >= 2 else "")
        ),
        assumptions    = assumptions,
        operations     = operations,
    )

    new_ops = append_compound_features(
        [op.model_dump() if hasattr(op, "model_dump") else op for op in graph.operations],
        prompt,
    )
    return OperationGraph(
        schema_version = graph.schema_version,
        part_family    = graph.part_family,
        part_name      = graph.part_name,
        reasoning      = graph.reasoning,
        assumptions    = graph.assumptions,
        operations     = new_ops,
    )
