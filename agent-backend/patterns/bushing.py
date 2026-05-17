"""
Deterministic bushing pattern — cylinder with a concentric through-hole.

A bushing is one of the most common engineering parts: a cylinder with an
inner bore (often press-fit, oil-impregnated, or used as a bearing).

Supported prompt forms:
  "create a bushing 30mm OD 15mm ID 40mm long"
  "make a bushing 25mm outer 12mm inner 30mm long"
  "bushing 40x20x50mm"  → first/larger is OD, second is ID, third is length
  "bronze bushing OD 30 ID 15 length 40"
"""
from __future__ import annotations

import re
from typing import Optional

from models.schemas import OperationGraph


_BUSHING_KW = re.compile(
    r"\b(bushing|bush|sleeve\s+bearing|bearing\s+sleeve)\b",
    re.IGNORECASE,
)
_NAMED_FORM = re.compile(
    r"(?P<od>\d+(?:\.\d+)?)\s*(?:mm)?\s*(?:OD|outer\s+diameter|outer)\b.*?"
    r"(?P<id>\d+(?:\.\d+)?)\s*(?:mm)?\s*(?:ID|inner\s+diameter|inner|bore)\b.*?"
    r"(?P<len>\d+(?:\.\d+)?)\s*(?:mm)?\s*(?:long|length|tall)?",
    re.IGNORECASE | re.DOTALL,
)
_TRIPLE_NOTATION = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:mm)?\s*[xX×]\s*(\d+(?:\.\d+)?)\s*(?:mm)?\s*[xX×]\s*(\d+(?:\.\d+)?)\s*(?:mm)?",
    re.IGNORECASE,
)


def match(prompt: str) -> tuple[float, float, float] | None:
    """Return (od_mm, id_mm, length_mm), where id < od."""
    if not _BUSHING_KW.search(prompt):
        return None
    m = _NAMED_FORM.search(prompt)
    if m:
        od = float(m.group("od"))
        id_ = float(m.group("id"))
        length = float(m.group("len"))
        return od, id_, length
    m = _TRIPLE_NOTATION.search(prompt)
    if m:
        a, b, c = float(m.group(1)), float(m.group(2)), float(m.group(3))
        # OD must be larger than ID. We assume the order is OD, ID, length
        # (most natural reading), but enforce OD>ID.
        if a > b:
            return a, b, c
        return b, a, c
    return None


def build_graph(od_mm: float, id_mm: float, length_mm: float) -> OperationGraph:
    if id_mm >= od_mm:
        # Defensive — caller should already enforce this.
        id_mm = od_mm * 0.5

    return OperationGraph(
        schema_version = "0.2",
        part_family    = "bushing_v0",
        part_name      = "bushing",
        reasoning      = (
            f"Deterministic bushing: OD {od_mm} mm, ID {id_mm} mm, length {length_mm} mm"
        ),
        assumptions    = [
            f"Bushing OD {od_mm:g} mm x ID {id_mm:g} mm x {length_mm:g} mm long on Front Plane",
            f"Wall thickness {(od_mm - id_mm) / 2:.2f} mm",
        ],
        operations     = [
            {"id": "p1",  "type": "create_part"},
            # Outer cylinder
            {"id": "sk1", "type": "create_sketch",  "plane": "Front Plane", "sketch_id": "sk1"},
            {"id": "c1",  "type": "add_circles",    "sketch_id": "sk1",
             "circles": [{"center": [0.0, 0.0], "diameter": od_mm}], "units": "mm"},
            {"id": "e1",  "type": "extrude_boss",   "profile_id": "sk1", "depth_mm": length_mm},
            # Inner bore (cut)
            {"id": "sk2", "type": "create_sketch",  "plane": "Front Plane", "sketch_id": "sk2"},
            {"id": "c2",  "type": "add_circles",    "sketch_id": "sk2",
             "circles": [{"center": [0.0, 0.0], "diameter": id_mm}], "units": "mm"},
            {"id": "e2",  "type": "extrude_cut",    "profile_id": "sk2",
             "through_all": True, "depth_mm": length_mm},
            {"id": "rb1", "type": "rebuild"},
        ],
    )


def try_generate(prompt: str) -> Optional[OperationGraph]:
    dims = match(prompt)
    if dims is None:
        return None
    return build_graph(*dims)
