"""
Deterministic washer pattern (ISO 7089 plain washer geometry).

Supported prompt forms:
  "create an M6 washer"
  "M8 washer ISO 7089"
  "M10 plain washer"
  "make a washer 10mm OD 4mm ID 1mm thick"
"""
from __future__ import annotations

import re
from typing import Optional

from models.schemas import OperationGraph


_WASHER_KW = re.compile(r"\b(washer)\b", re.IGNORECASE)
_BOLT = re.compile(r"\bM(\d{1,2})\b", re.IGNORECASE)
_EXPLICIT = re.compile(
    r"(\d+(?:\.\d+)?)\s*mm\s*(?:OD|outer)\b.*?"
    r"(\d+(?:\.\d+)?)\s*mm\s*(?:ID|inner|bore)\b.*?"
    r"(\d+(?:\.\d+)?)\s*mm\s+thick",
    re.IGNORECASE | re.DOTALL,
)


# ISO 7089 plain washer geometry — inner diameter, outer diameter, thickness (mm)
_ISO_7089 = {
    "M3":  (3.2, 7.0, 0.5),
    "M4":  (4.3, 9.0, 0.8),
    "M5":  (5.3, 10.0, 1.0),
    "M6":  (6.4, 12.0, 1.6),
    "M8":  (8.4, 16.0, 1.6),
    "M10": (10.5, 20.0, 2.0),
    "M12": (13.0, 24.0, 2.5),
    "M16": (17.0, 30.0, 3.0),
    "M20": (21.0, 37.0, 3.0),
    "M24": (25.0, 44.0, 4.0),
}


def try_generate(prompt: str) -> Optional[OperationGraph]:
    if not _WASHER_KW.search(prompt):
        return None

    m = _EXPLICIT.search(prompt)
    if m:
        od, id_, thickness = float(m.group(1)), float(m.group(2)), float(m.group(3))
        return _build(od, id_, thickness, fastener="custom")

    bm = _BOLT.search(prompt)
    if bm:
        fastener = f"M{bm.group(1)}"
        if fastener in _ISO_7089:
            id_, od, thickness = _ISO_7089[fastener]
            return _build(od, id_, thickness, fastener=fastener)

    return None


def _build(od: float, id_: float, thickness: float, fastener: str) -> OperationGraph:
    return OperationGraph(
        schema_version = "0.2",
        part_family    = "washer_v0",
        part_name      = "washer",
        reasoning      = f"ISO 7089 {fastener} washer: OD {od} ID {id_} t {thickness}",
        assumptions    = [
            f"ISO 7089 {fastener} plain washer (OD {od:g} mm, ID {id_:g} mm, t {thickness:g} mm)",
        ],
        operations     = [
            {"id": "p1",  "type": "create_part"},
            {"id": "sk1", "type": "create_sketch",  "plane": "Front Plane", "sketch_id": "sk1"},
            {"id": "c1",  "type": "add_circles",    "sketch_id": "sk1",
             "circles": [{"center": [0.0, 0.0], "diameter": od}], "units": "mm"},
            {"id": "e1",  "type": "extrude_boss",   "profile_id": "sk1", "depth_mm": thickness},
            {"id": "sk2", "type": "create_sketch",  "plane": "Front Plane", "sketch_id": "sk2"},
            {"id": "c2",  "type": "add_circles",    "sketch_id": "sk2",
             "circles": [{"center": [0.0, 0.0], "diameter": id_}], "units": "mm"},
            {"id": "e2",  "type": "extrude_cut",    "profile_id": "sk2",
             "through_all": True, "depth_mm": thickness},
            {"id": "rb1", "type": "rebuild"},
        ],
    )
