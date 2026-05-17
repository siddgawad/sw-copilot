"""
Deterministic plate pattern — flat rectangular plate, optionally with corner
holes. No LLM required.

Supported prompt forms:
  "create a 100x100x5mm plate"
  "make a plate 200mm x 150mm x 6mm"
  "plate 100 by 60 by 5"
  "create a plate 100x100mm 5mm thick"
  "mounting plate 80x60x4mm with 4 M5 holes at corners"
  "plate 120x80x6mm with 6 M8 holes at corners"

A "plate" is any rectangular flat part where one dimension (the thickness) is
notably smaller than the other two. We use the smallest dimension as the
thickness (extrude depth) and the other two as the in-plane size.
"""
from __future__ import annotations

import re
from typing import Optional

from models.schemas import OperationGraph
from patterns.compound_features import append_compound_features
from standards.dimension_resolver import resolve_clearance_hole, resolve_counterbore


_PLATE_KW = re.compile(
    r"\b(plate|mounting\s+plate|base\s+plate|flat\s+plate)\b",
    re.IGNORECASE,
)
_DIM_PATTERN = r"(\d+(?:\.\d+)?)"
_X_NOTATION = re.compile(
    rf"{_DIM_PATTERN}\s*(?:mm)?\s*[xX×]\s*{_DIM_PATTERN}\s*(?:mm)?\s*[xX×]\s*{_DIM_PATTERN}\s*(?:mm)?",
    re.IGNORECASE,
)
_BY_NOTATION = re.compile(
    rf"{_DIM_PATTERN}\s*(?:mm)?\s+by\s+{_DIM_PATTERN}\s*(?:mm)?\s+by\s+{_DIM_PATTERN}",
    re.IGNORECASE,
)
_THICK_NOTATION = re.compile(
    rf"{_DIM_PATTERN}\s*(?:mm)?\s*[xX×]\s*{_DIM_PATTERN}\s*(?:mm)?\s*,?\s*{_DIM_PATTERN}\s*mm\s+thick",
    re.IGNORECASE,
)
_FASTENER_AT_CORNERS = re.compile(
    r"\b(?:(\d+|four|six|eight)\s+)?M(\d{1,2})\s+(?:counterbored?|countersunk|tapped)?\s*holes?\s+at\s+(?:the\s+)?corners?",
    re.IGNORECASE,
)
_HOLE_TYPE_HINT = re.compile(
    r"\b(counterbore|counterbored|countersink|countersunk|tap|tapped)\b",
    re.IGNORECASE,
)
_PLANE_HINT = re.compile(
    r"\bon\s+(?:the\s+)?(top|front|right)\s*plane\b",
    re.IGNORECASE,
)


def _hole_type(prompt: str) -> str:
    m = _HOLE_TYPE_HINT.search(prompt)
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


def _hole_count(token: str | None, plural: bool = False) -> int:
    if not token:
        return 4 if plural else 1
    token = token.lower()
    if token.isdigit():
        return int(token)
    return {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "eight": 8}.get(token, 4)


def _sketch_plane(prompt: str) -> str:
    # Default: Front Plane (XY). Extrude direction is +Z, so the body's bbox is
    # length × width × thickness on (X, Y, Z) respectively. The C# executor's
    # SelectTopFaceOfBody picks the highest-Z face, which is the plate's top
    # face. Hole positions in (x_mm, y_mm) then map directly to world (X, Y).
    m = _PLANE_HINT.search(prompt)
    if not m:
        return "Front Plane"
    keyword = m.group(1).lower()
    return {"top": "Top Plane", "front": "Front Plane", "right": "Right Plane"}[keyword]


def _parse_dims(prompt: str) -> tuple[float, float, float] | None:
    """Return (length, width, thickness) in mm, ordered with thickness smallest."""
    m = _THICK_NOTATION.search(prompt)
    if m:
        l, w, t = float(m.group(1)), float(m.group(2)), float(m.group(3))
        return l, w, t

    m = _X_NOTATION.search(prompt)
    if m:
        a, b, c = float(m.group(1)), float(m.group(2)), float(m.group(3))
        return _order_dims(a, b, c)

    m = _BY_NOTATION.search(prompt)
    if m:
        a, b, c = float(m.group(1)), float(m.group(2)), float(m.group(3))
        return _order_dims(a, b, c)

    return None


def _order_dims(a: float, b: float, c: float) -> tuple[float, float, float]:
    """Order so the smallest dim becomes thickness (last)."""
    dims = sorted([a, b, c])
    thickness = dims[0]
    # length and width are the larger two — keep order stable for length > width.
    rest = sorted([dims[1], dims[2]], reverse=True)
    return rest[0], rest[1], thickness


def match(prompt: str) -> tuple[float, float, float] | None:
    if not _PLATE_KW.search(prompt):
        return None
    return _parse_dims(prompt)


def build_graph(
    length: float,
    width: float,
    thickness: float,
    plane: str = "Front Plane",
    bolt_count: int = 0,
    bolt_size: str = "M6",
    hole_type: str = "simple",
) -> OperationGraph:
    operations = [
        {"id": "p1",  "type": "create_part"},
        {"id": "sk1", "type": "create_sketch",        "plane": plane, "sketch_id": "sk1"},
        {"id": "r1",  "type": "add_center_rectangle", "sketch_id": "sk1",
         "center": [0.0, 0.0], "length": length, "width": width},
        {"id": "e1",  "type": "extrude_boss",         "profile_id": "sk1", "depth_mm": thickness},
    ]

    assumptions = [
        f"Plate {length:g} x {width:g} x {thickness:g} mm on {plane}",
    ]

    if bolt_count >= 2:
        # Compute hole positions at the corners with safe edge inset.
        clearance = resolve_clearance_hole(bolt_size) or {"diameter_mm": 7.0}
        diameter = float(clearance["diameter_mm"])
        if hole_type == "counterbore":
            cb = resolve_counterbore(bolt_size)
            if cb:
                diameter = float(cb["counterbore_diameter_mm"])

        min_inset = diameter / 2.0 + 2.0
        max_inset = (min(length, width) - diameter) / 2.0
        if max_inset >= min_inset:
            inset = min(10.0, max_inset)
            if inset < min_inset:
                inset = min_inset
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
                "hole_type":     hole_type,
                "fastener_size": bolt_size,
                "through_all":   True,
                "depth_mm":      0.0,
                "positions":     positions,
            })
            assumptions.append(
                f"{bolt_count}x {bolt_size} {hole_type} holes at corners with "
                f"{inset:g} mm inset (ISO 273 clearance dia {diameter:g} mm)"
            )

    operations.append({"id": "rb1", "type": "rebuild"})

    return OperationGraph(
        schema_version = "0.2",
        part_family    = "plate_v0",
        part_name      = "plate",
        reasoning      = (
            f"Deterministic plate fast path: {length} x {width} x {thickness} mm "
            f"on {plane}"
            + (f", {bolt_count}x {bolt_size} corner holes" if bolt_count >= 2 else "")
        ),
        assumptions    = assumptions,
        operations     = operations,
    )


def try_generate(prompt: str) -> Optional[OperationGraph]:
    dims = match(prompt)
    if dims is None:
        return None
    length, width, thickness = dims
    plane = _sketch_plane(prompt)

    bolt_count = 0
    bolt_size = "M6"
    hole_type = _hole_type(prompt)
    fm = _FASTENER_AT_CORNERS.search(prompt)
    if fm:
        bolt_count = _hole_count(fm.group(1), plural=True)
        bolt_size = f"M{fm.group(2)}"

    graph = build_graph(
        length=length,
        width=width,
        thickness=thickness,
        plane=plane,
        bolt_count=bolt_count,
        bolt_size=bolt_size,
        hole_type=hole_type,
    )

    # Compound: if the prompt also asks for fillet / chamfer in one shot,
    # append those ops before the final rebuild.
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
