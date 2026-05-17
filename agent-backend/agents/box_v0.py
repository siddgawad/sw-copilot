"""Deterministic parser for box/rectangular-block prompts. No LLM required."""
import re
from typing import Optional
from models.schemas import OperationGraph


# Matches: "50mm wide 30mm deep 20mm tall box", "100x60x40mm block",
#          "50 by 30 by 20 rectangular block", "box 80mm 40mm 25mm"
_LABELED = re.compile(
    r"(\d+(?:\.\d+)?)\s*mm\s+wide.*?(\d+(?:\.\d+)?)\s*mm\s+deep.*?(\d+(?:\.\d+)?)\s*mm\s+tall",
    re.IGNORECASE,
)
_X_NOTATION = re.compile(
    r"(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)\s*mm",
    re.IGNORECASE,
)
_BY_NOTATION = re.compile(
    r"(\d+(?:\.\d+)?)\s+by\s+(\d+(?:\.\d+)?)\s+by\s+(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_DIM_WITH_OPTIONAL_UNIT = r"(\d+(?:\.\d+)?)\s*(?:mm)?"
_X_NOTATION = re.compile(
    rf"{_DIM_WITH_OPTIONAL_UNIT}\s*[xX]\s*{_DIM_WITH_OPTIONAL_UNIT}\s*[xX]\s*{_DIM_WITH_OPTIONAL_UNIT}\s*(?:mm)?",
    re.IGNORECASE,
)
_BY_NOTATION = re.compile(
    rf"{_DIM_WITH_OPTIONAL_UNIT}\s+by\s+{_DIM_WITH_OPTIONAL_UNIT}\s+by\s+{_DIM_WITH_OPTIONAL_UNIT}",
    re.IGNORECASE,
)
_BOX_KEYWORD = re.compile(r"\b(box|block|rectangular\s+block|cube)\b", re.IGNORECASE)
_THREE_NUMS = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*mm\b[^,\n]{0,20}\b(\d+(?:\.\d+)?)\s*mm\b[^,\n]{0,20}\b(\d+(?:\.\d+)?)\s*mm\b",
    re.IGNORECASE,
)


def match(prompt: str) -> Optional[tuple[float, float, float]]:
    """Return (width_mm, depth_mm, height_mm) if prompt describes a box, else None."""
    if not _BOX_KEYWORD.search(prompt):
        return None

    m = _LABELED.search(prompt)
    if m:
        return float(m.group(1)), float(m.group(2)), float(m.group(3))

    m = _X_NOTATION.search(prompt)
    if m:
        return float(m.group(1)), float(m.group(2)), float(m.group(3))

    m = _BY_NOTATION.search(prompt)
    if m:
        return float(m.group(1)), float(m.group(2)), float(m.group(3))

    m = _THREE_NUMS.search(prompt)
    if m:
        return float(m.group(1)), float(m.group(2)), float(m.group(3))

    return None


def build_graph(width: float, depth: float, height: float) -> OperationGraph:
    return OperationGraph(
        schema_version="0.2",
        part_family="box_v0",
        part_name="box",
        reasoning=f"Deterministic box fast path: {width}×{depth}×{height} mm",
        operations=[
            {"id": "p1",  "type": "create_part"},
            {"id": "sk1", "type": "create_sketch",         "plane": "Front Plane", "sketch_id": "sk1"},
            {"id": "r1",  "type": "add_center_rectangle",  "sketch_id": "sk1",
             "center": [0.0, 0.0], "length": width, "width": depth},
            {"id": "e1",  "type": "extrude_boss",          "profile_id": "sk1", "depth_mm": height},
            {"id": "rb1", "type": "rebuild"},
        ],
    )


def try_generate(prompt: str) -> Optional[OperationGraph]:
    dims = match(prompt)
    if dims is None:
        return None
    return build_graph(*dims)
