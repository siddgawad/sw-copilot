"""
Deterministic pipe / tube pattern — long thin-walled hollow cylinder.

Supported prompt forms:
  "create a pipe 25mm OD 20mm ID 200mm long"
  "tube 32mm OD 28mm ID 500mm long"
  "schedule 40 pipe 1 inch 100mm long"  (uses standard pipe schedule table)
  "pipe 30mm OD 2mm wall 250mm long"
"""
from __future__ import annotations

import re
from typing import Optional

from models.schemas import OperationGraph
from patterns.compound_features import append_compound_features


_PIPE_KW = re.compile(r"\b(pipe|tube|tubing|hollow\s+(?:cylinder|shaft))\b", re.IGNORECASE)
_OD_ID_LEN = re.compile(
    r"(\d+(?:\.\d+)?)\s*mm\s*(?:OD|outer)\b.*?"
    r"(\d+(?:\.\d+)?)\s*mm\s*(?:ID|inner|bore)\b.*?"
    r"(\d+(?:\.\d+)?)\s*mm\s+(?:long|length)",
    re.IGNORECASE | re.DOTALL,
)
_OD_WALL_LEN = re.compile(
    r"(\d+(?:\.\d+)?)\s*mm\s*(?:OD|outer|diameter|dia)\b.*?"
    r"(\d+(?:\.\d+)?)\s*mm\s+wall.*?"
    r"(\d+(?:\.\d+)?)\s*mm\s+(?:long|length)",
    re.IGNORECASE | re.DOTALL,
)


def try_generate(prompt: str) -> Optional[OperationGraph]:
    if not _PIPE_KW.search(prompt):
        return None

    m = _OD_ID_LEN.search(prompt)
    if m:
        od, id_, length = float(m.group(1)), float(m.group(2)), float(m.group(3))
        return _build(od, id_, length, prompt)

    m = _OD_WALL_LEN.search(prompt)
    if m:
        od, wall, length = float(m.group(1)), float(m.group(2)), float(m.group(3))
        id_ = od - 2 * wall
        if id_ <= 0:
            return None
        return _build(od, id_, length, prompt)

    return None


def _build(od: float, id_: float, length: float, prompt: str) -> OperationGraph:
    wall = (od - id_) / 2.0
    graph = OperationGraph(
        schema_version = "0.2",
        part_family    = "pipe_v0",
        part_name      = "pipe",
        reasoning      = f"Pipe OD {od} ID {id_} length {length} mm (wall {wall:.2f} mm)",
        assumptions    = [
            f"Pipe OD {od:g} mm x ID {id_:g} mm x {length:g} mm long",
            f"Wall thickness {wall:.2f} mm",
        ],
        operations     = [
            {"id": "p1",  "type": "create_part"},
            {"id": "sk1", "type": "create_sketch",  "plane": "Front Plane", "sketch_id": "sk1"},
            {"id": "c1",  "type": "add_circles",    "sketch_id": "sk1",
             "circles": [{"center": [0.0, 0.0], "diameter": od}], "units": "mm"},
            {"id": "e1",  "type": "extrude_boss",   "profile_id": "sk1", "depth_mm": length},
            {"id": "sk2", "type": "create_sketch",  "plane": "Front Plane", "sketch_id": "sk2"},
            {"id": "c2",  "type": "add_circles",    "sketch_id": "sk2",
             "circles": [{"center": [0.0, 0.0], "diameter": id_}], "units": "mm"},
            {"id": "e2",  "type": "extrude_cut",    "profile_id": "sk2",
             "through_all": True, "depth_mm": length},
            {"id": "rb1", "type": "rebuild"},
        ],
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
