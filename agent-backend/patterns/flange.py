"""
Deterministic flange pattern — circular disk with optional bolt circle.

Supported prompt forms:
  "create a flange 100mm OD 6mm thick"
  "flange 80mm diameter 5mm thick with 4 M6 holes on 60mm PCD"
  "flange 120mm 8mm thick 6 M8 holes 90mm pitch circle"
  "circular flange 100mm dia 5mm with 8 M6 bolt holes on 75mm PCD"

This is one of the most common fabricated parts in industry: a round plate
with a bolt circle. It maps onto our existing 25 ops cleanly:
  sketch (circle on Front Plane) -> extrude -> hole_wizard at one position
  -> circular_pattern on PCD.
"""
from __future__ import annotations

import re
from typing import Optional

from models.schemas import OperationGraph
from standards.dimension_resolver import resolve_clearance_hole


_FLANGE_KW = re.compile(r"\b(flange|disc|disk|round\s+plate|circular\s+flange)\b", re.IGNORECASE)
_DIAMETER = re.compile(
    r"(?:(?P<num>\d+(?:\.\d+)?)\s*mm\s*(?:OD|diameter|dia|outer\s+diameter)|"
    r"(?:OD|diameter|dia)\s*(?P<num2>\d+(?:\.\d+)?))",
    re.IGNORECASE,
)
_THICKNESS = re.compile(
    r"(\d+(?:\.\d+)?)\s*mm\s+thick",
    re.IGNORECASE,
)
_FIRST_TWO_DIMS = re.compile(
    r"(\d+(?:\.\d+)?)\s*mm\b[^,\n]{0,40}\b(\d+(?:\.\d+)?)\s*mm\b",
    re.IGNORECASE,
)
_BOLT_CIRCLE = re.compile(
    r"\b(\d+|two|three|four|five|six|seven|eight|nine|ten|twelve)\s+M(\d{1,2})\s+"
    r"(?:bolt\s+|hex\s+|cap\s+screw\s+|machine\s+screw\s+)?"
    r"(?:clearance\s+|counterbored\s+|countersunk\s+|tapped\s+)?holes?\s+"
    r"(?:on\s+(?:a\s+)?|at\s+|spaced\s+at\s+)?"
    r"(?:a\s+)?(\d+(?:\.\d+)?)\s*mm\s*(?:PCD|pitch\s+circle|bolt\s+circle|BCD|diameter)",
    re.IGNORECASE,
)
_HOLE_TYPE = re.compile(
    r"\b(counterbored?|countersink|countersunk|tapped)\b",
    re.IGNORECASE,
)


def _count_word(word: str) -> int:
    if word.isdigit():
        return int(word)
    return {
        "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
        "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12,
    }.get(word.lower(), 4)


def _hole_type(prompt: str) -> str:
    m = _HOLE_TYPE.search(prompt)
    if not m:
        return "simple"
    kind = m.group(1).lower()
    if kind.startswith("counterbore") or kind.startswith("counterbored"):
        return "counterbore"
    if kind.startswith("countersink") or kind.startswith("countersunk"):
        return "countersink"
    if kind.startswith("tap"):
        return "tapped"
    return "simple"


def _parse_diameter(prompt: str) -> float | None:
    m = _DIAMETER.search(prompt)
    if not m:
        return None
    val = m.group("num") or m.group("num2")
    return float(val) if val else None


def _parse_thickness(prompt: str) -> float | None:
    m = _THICKNESS.search(prompt)
    if not m:
        return None
    return float(m.group(1))


def _parse_two_dims(prompt: str) -> tuple[float, float] | None:
    """Fallback: extract the first two mm numbers in the prompt."""
    m = _FIRST_TWO_DIMS.search(prompt)
    if not m:
        return None
    return float(m.group(1)), float(m.group(2))


def match(prompt: str) -> tuple[float, float] | None:
    """Return (od_mm, thickness_mm) or None."""
    if not _FLANGE_KW.search(prompt):
        return None

    od = _parse_diameter(prompt)
    th = _parse_thickness(prompt)
    if od is not None and th is not None:
        return od, th

    # Fallback: first two dimensions in mm.
    fb = _parse_two_dims(prompt)
    if fb:
        a, b = fb
        # Larger one is OD, smaller is thickness.
        return (a, b) if a >= b else (b, a)

    return None


def build_graph(
    od_mm: float,
    thickness_mm: float,
    bolt_count: int = 0,
    bolt_size: str = "M6",
    bolt_pcd_mm: float = 0.0,
    hole_type: str = "simple",
) -> OperationGraph:
    operations: list[dict] = [
        {"id": "p1",  "type": "create_part"},
        {"id": "sk1", "type": "create_sketch",        "plane": "Front Plane", "sketch_id": "sk1"},
        {"id": "c1",  "type": "add_circles",          "sketch_id": "sk1",
         "circles": [{"center": [0.0, 0.0], "diameter": od_mm}], "units": "mm"},
        {"id": "e1",  "type": "extrude_boss",         "profile_id": "sk1", "depth_mm": thickness_mm},
    ]

    assumptions = [
        f"Flange OD {od_mm:g} mm x {thickness_mm:g} mm thick on Front Plane"
    ]

    if bolt_count >= 2 and bolt_pcd_mm > 0:
        clearance = resolve_clearance_hole(bolt_size) or {"diameter_mm": 7.0}
        radius = bolt_pcd_mm / 2.0
        # Place the seed hole at (PCD/2, 0), then circular pattern.
        operations.append({
            "id":            "h1",
            "type":          "hole_wizard",
            "face_of":       "e1",
            "hole_type":     hole_type,
            "fastener_size": bolt_size,
            "through_all":   True,
            "depth_mm":      0.0,
            "positions":     [{"x_mm": radius, "y_mm": 0.0}],
        })
        operations.append({
            "id":         "cp1",
            "type":       "circular_pattern",
            "source_ids": ["h1"],
            "count":      bolt_count,
            "pcd_mm":     bolt_pcd_mm,
        })
        assumptions.append(
            f"{bolt_count}x {bolt_size} {hole_type} holes on {bolt_pcd_mm:g} mm PCD "
            f"(clearance dia {clearance['diameter_mm']:g} mm)"
        )

    operations.append({"id": "rb1", "type": "rebuild"})

    return OperationGraph(
        schema_version = "0.2",
        part_family    = "flange_v0",
        part_name      = "flange",
        reasoning      = (
            f"Deterministic flange: OD {od_mm} mm x {thickness_mm} mm thick"
            + (f", {bolt_count}x {bolt_size} on {bolt_pcd_mm} PCD" if bolt_count >= 2 else "")
        ),
        assumptions    = assumptions,
        operations     = operations,
    )


def try_generate(prompt: str) -> Optional[OperationGraph]:
    dims = match(prompt)
    if dims is None:
        return None
    od_mm, thickness_mm = dims

    bolt_count = 0
    bolt_size = "M6"
    bolt_pcd_mm = 0.0
    hole_type = _hole_type(prompt)

    bm = _BOLT_CIRCLE.search(prompt)
    if bm:
        bolt_count = _count_word(bm.group(1))
        bolt_size = f"M{bm.group(2)}"
        bolt_pcd_mm = float(bm.group(3))

    return build_graph(
        od_mm        = od_mm,
        thickness_mm = thickness_mm,
        bolt_count   = bolt_count,
        bolt_size    = bolt_size,
        bolt_pcd_mm  = bolt_pcd_mm,
        hole_type    = hole_type,
    )
