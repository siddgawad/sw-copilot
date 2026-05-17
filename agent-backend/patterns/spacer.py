"""
Deterministic spacer pattern.

A spacer is a short flat part (plate or cylindrical) with a single concentric
hole used to maintain distance between two components.

Supported prompt forms:
  "create a spacer 30mm OD 10mm ID 5mm thick"
  "round spacer 25mm dia 8mm bore 5mm thick"
  "create a square spacer 30x30mm with 12mm hole 5mm thick"
  "rectangular spacer 40x20mm 10mm bore 5mm thick"
"""
from __future__ import annotations

import re
from typing import Optional

from models.schemas import OperationGraph
from patterns.compound_features import append_compound_features


_SPACER_KW    = re.compile(r"\b(spacer)\b", re.IGNORECASE)
_ROUND_HINT   = re.compile(r"\b(round|circular|disc|disk)\b", re.IGNORECASE)
_SQUARE_HINT  = re.compile(r"\b(square|rectangular|rect)\b", re.IGNORECASE)
_OD_FORM      = re.compile(
    r"(\d+(?:\.\d+)?)\s*mm\s*(?:OD|outer|diameter|dia)\b.*?"
    r"(\d+(?:\.\d+)?)\s*mm\s*(?:ID|inner|bore)\b.*?"
    r"(\d+(?:\.\d+)?)\s*mm\s+thick",
    re.IGNORECASE | re.DOTALL,
)
_SQUARE_FORM  = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:mm)?\s*[xX×]\s*(\d+(?:\.\d+)?)\s*mm.*?"
    r"(\d+(?:\.\d+)?)\s*mm\s+(?:bore|hole|id|inner).*?"
    r"(\d+(?:\.\d+)?)\s*mm\s+thick",
    re.IGNORECASE | re.DOTALL,
)


def try_generate(prompt: str) -> Optional[OperationGraph]:
    if not _SPACER_KW.search(prompt):
        return None

    # Round (cylindrical) spacer.
    m = _OD_FORM.search(prompt)
    if m:
        od, bore, thickness = float(m.group(1)), float(m.group(2)), float(m.group(3))
        return _build_round_spacer(od, bore, thickness, prompt)

    # Square / rectangular spacer.
    m = _SQUARE_FORM.search(prompt)
    if m:
        length, width = float(m.group(1)), float(m.group(2))
        bore, thickness = float(m.group(3)), float(m.group(4))
        return _build_square_spacer(length, width, bore, thickness, prompt)

    return None


def _build_round_spacer(od: float, bore: float, thickness: float, prompt: str) -> OperationGraph:
    graph = OperationGraph(
        schema_version = "0.2",
        part_family    = "spacer_v0",
        part_name      = "spacer",
        reasoning      = f"Round spacer OD {od} ID {bore} thick {thickness} mm",
        assumptions    = [
            f"Cylindrical spacer OD {od:g} mm x ID {bore:g} mm x {thickness:g} mm thick",
        ],
        operations     = [
            {"id": "p1",  "type": "create_part"},
            {"id": "sk1", "type": "create_sketch",  "plane": "Front Plane", "sketch_id": "sk1"},
            {"id": "c1",  "type": "add_circles",    "sketch_id": "sk1",
             "circles": [{"center": [0.0, 0.0], "diameter": od}], "units": "mm"},
            {"id": "e1",  "type": "extrude_boss",   "profile_id": "sk1", "depth_mm": thickness},
            {"id": "sk2", "type": "create_sketch",  "plane": "Front Plane", "sketch_id": "sk2"},
            {"id": "c2",  "type": "add_circles",    "sketch_id": "sk2",
             "circles": [{"center": [0.0, 0.0], "diameter": bore}], "units": "mm"},
            {"id": "e2",  "type": "extrude_cut",    "profile_id": "sk2",
             "through_all": True, "depth_mm": thickness},
            {"id": "rb1", "type": "rebuild"},
        ],
    )
    return _apply_compound(graph, prompt)


def _build_square_spacer(length: float, width: float, bore: float, thickness: float, prompt: str) -> OperationGraph:
    graph = OperationGraph(
        schema_version = "0.2",
        part_family    = "spacer_v0",
        part_name      = "spacer",
        reasoning      = f"Square spacer {length}x{width} bore {bore} thick {thickness} mm",
        assumptions    = [
            f"Rectangular spacer {length:g} x {width:g} mm x {thickness:g} mm thick "
            f"with {bore:g} mm bore",
        ],
        operations     = [
            {"id": "p1",  "type": "create_part"},
            {"id": "sk1", "type": "create_sketch",         "plane": "Top Plane", "sketch_id": "sk1"},
            {"id": "r1",  "type": "add_center_rectangle",  "sketch_id": "sk1",
             "center": [0.0, 0.0], "length": length, "width": width},
            {"id": "e1",  "type": "extrude_boss",          "profile_id": "sk1", "depth_mm": thickness},
            {"id": "sk2", "type": "create_sketch",         "plane": "Top Plane", "sketch_id": "sk2"},
            {"id": "c2",  "type": "add_circles",           "sketch_id": "sk2",
             "circles": [{"center": [0.0, 0.0], "diameter": bore}], "units": "mm"},
            {"id": "e2",  "type": "extrude_cut",           "profile_id": "sk2",
             "through_all": True, "depth_mm": thickness},
            {"id": "rb1", "type": "rebuild"},
        ],
    )
    return _apply_compound(graph, prompt)


def _apply_compound(graph: OperationGraph, prompt: str) -> OperationGraph:
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
