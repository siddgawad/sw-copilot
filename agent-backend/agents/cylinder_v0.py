"""Deterministic parser for cylinder/shaft prompts. No LLM required."""
import re
from typing import Optional
from models.schemas import OperationGraph


# Matches: "40mm diameter shaft 100mm long", "cylinder 30mm radius 50mm tall"
_DIAM_THEN_LEN = re.compile(
    r"(\d+(?:\.\d+)?)\s*mm\s+diameter\b.*?(\d+(?:\.\d+)?)\s*mm\s+(?:long|tall|length|height)",
    re.IGNORECASE,
)
_RAD_THEN_LEN = re.compile(
    r"(\d+(?:\.\d+)?)\s*mm\s+radius\b.*?(\d+(?:\.\d+)?)\s*mm\s+(?:long|tall|length|height)",
    re.IGNORECASE,
)
_LEN_THEN_DIAM = re.compile(
    r"(\d+(?:\.\d+)?)\s*mm\s+(?:long|tall|length|height).*?(\d+(?:\.\d+)?)\s*mm\s+diameter",
    re.IGNORECASE,
)
# "30mm circle extruded 60mm"
_CIRCLE_EXTRUDED = re.compile(
    r"(\d+(?:\.\d+)?)\s*mm\s+circle\b.*?(\d+(?:\.\d+)?)\s*mm",
    re.IGNORECASE,
)
_CYL_KEYWORD = re.compile(
    r"\b(cylinder|shaft|rod|pin|boss|circle\s+extruded|circular\s+extrusion)\b",
    re.IGNORECASE,
)


def match(prompt: str) -> Optional[tuple[float, float]]:
    """Return (radius_mm, length_mm) if prompt describes a cylinder, else None."""
    if not _CYL_KEYWORD.search(prompt):
        return None

    m = _DIAM_THEN_LEN.search(prompt)
    if m:
        return float(m.group(1)) / 2.0, float(m.group(2))

    m = _RAD_THEN_LEN.search(prompt)
    if m:
        return float(m.group(1)), float(m.group(2))

    m = _LEN_THEN_DIAM.search(prompt)
    if m:
        return float(m.group(2)) / 2.0, float(m.group(1))

    m = _CIRCLE_EXTRUDED.search(prompt)
    if m:
        # "Nmm circle" without qualifier → treat as diameter
        return float(m.group(1)) / 2.0, float(m.group(2))

    return None


def build_graph(radius: float, length: float) -> OperationGraph:
    return OperationGraph(
        schema_version="0.2",
        part_name="cylinder",
        reasoning=f"Deterministic cylinder fast path: r={radius} mm, l={length} mm",
        operations=[
            {"id": "p1",  "type": "create_part"},
            {"id": "sk1", "type": "create_sketch", "plane": "Front Plane", "sketch_id": "sk1"},
            {"id": "c1",  "type": "add_circles",   "sketch_id": "sk1",
             "circles": [{"center": [0.0, 0.0], "diameter": radius * 2}]},
            {"id": "e1",  "type": "extrude_boss",  "profile_id": "sk1", "depth_mm": length},
            {"id": "rb1", "type": "rebuild"},
        ],
    )


def try_generate(prompt: str) -> Optional[OperationGraph]:
    dims = match(prompt)
    if dims is None:
        return None
    return build_graph(*dims)
