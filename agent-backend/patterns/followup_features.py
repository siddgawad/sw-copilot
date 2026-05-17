"""Deterministic follow-up feature edits for an already-open part."""
from __future__ import annotations

import re
from typing import Optional

from models.schemas import DocumentContext, OperationGraph
from standards.dimension_resolver import (
    resolve_clearance_hole,
    resolve_counterbore,
    resolve_edge_inset,
)


_FASTENER = re.compile(r"\bM(\d{1,2})\b", re.IGNORECASE)
_EXPLICIT_INSET = re.compile(
    r"(\d+(?:\.\d+)?)\s*mm\s*(?:inset|edge\s*offset|offset|from\s+(?:the\s+)?edges?)",
    re.IGNORECASE,
)
_DISTANCE = re.compile(r"(\d+(?:\.\d+)?)\s*mm", re.IGNORECASE)
_FOUR = re.compile(r"\b(4|four)\b", re.IGNORECASE)


def try_generate(prompt: str, context: Optional[DocumentContext] = None) -> OperationGraph | None:
    hole_graph = _try_corner_holes(prompt, context)
    if hole_graph is not None:
        return hole_graph

    edge_graph = _try_edge_finish(prompt)
    if edge_graph is not None:
        return edge_graph

    return None


_NEW_SHAPE_KEYWORDS = (
    "plate", "box", "block", "flange", "disc", "disk", "bracket", "shaft",
    "cylinder", "bushing", "spacer", "gear", "washer", "pipe", "tube",
    "enclosure", "housing", "case", "chassis", "cabinet",
)


def _try_corner_holes(prompt: str, context: Optional[DocumentContext]) -> OperationGraph | None:
    text = prompt.lower()
    if "corner" not in text:
        return None
    if not any(word in text for word in ("hole", "holes", "counterbore", "counterbored", "countersink", "tapped")):
        return None

    # If the prompt also describes a NEW shape (plate / box / flange / etc.),
    # this is a compound prompt that the primary-shape pattern should own.
    # Stand down so the shape pattern (with embedded hole-at-corners support)
    # gets the request.
    if any(re.search(rf"\b{kw}\b", text) for kw in _NEW_SHAPE_KEYWORDS):
        return None

    if not _FOUR.search(prompt):
        return _needs_input("corner hole pattern", "number of holes; say four/4 for all corners")

    fastener = _fastener_size(prompt)
    hole_type = _hole_type(prompt)

    bbox = context.bounding_box_mm if context is not None else None
    if bbox is None:
        return _needs_input(
            "corner hole pattern",
            "active part bounding_box_mm; open a part or specify the part size",
        )

    x_size = float(bbox.x_mm)
    y_size = float(bbox.y_mm)
    if x_size <= 0 or y_size <= 0:
        return _needs_input("corner hole pattern", "valid X/Y part dimensions for corner coordinates")

    inset = _explicit_inset(prompt)
    inset_source = "explicit"
    if inset is None:
        inset = _default_inset(fastener)
        inset_source = "standard edge inset"

    diameter = _hole_outer_diameter(fastener, hole_type)
    minimum_inset = (diameter / 2.0) + 1.0

    # Inset must also keep adjacent hole centers at least `diameter` apart.
    # For 4 corner holes the limiting dimension is the shorter box side.
    max_inset_for_spacing = (min(x_size, y_size) - diameter) / 2.0
    if max_inset_for_spacing < minimum_inset:
        return _needs_input(
            "corner hole pattern",
            f"{fastener} {hole_type} holes (outer diameter {diameter:g} mm) cannot fit in {x_size:g} x {y_size:g} mm — box too small",
        )

    if inset < minimum_inset:
        inset = minimum_inset
        inset_source = "minimum edge clearance"
    if inset > max_inset_for_spacing:
        inset = max_inset_for_spacing
        inset_source = "tightest inset for 4-corner spacing"

    if x_size <= 2 * inset or y_size <= 2 * inset:
        return _needs_input(
            "corner hole pattern",
            f"hole inset small enough to fit {fastener} {hole_type} holes inside {x_size:g} x {y_size:g} mm",
        )

    x = (x_size / 2.0) - inset
    y = (y_size / 2.0) - inset
    positions = [
        {"x_mm": -x, "y_mm": -y},
        {"x_mm": x, "y_mm": -y},
        {"x_mm": -x, "y_mm": y},
        {"x_mm": x, "y_mm": y},
    ]

    assumptions = [
        f"{fastener} {hole_type} holes placed on the active top face",
        f"{inset:g} mm corner inset ({inset_source})",
    ]
    if hole_type == "counterbore":
        cbore = resolve_counterbore(fastener)
        if cbore:
            assumptions.append(
                f"ISO 4762 counterbore: diameter {cbore['counterbore_diameter_mm']:g} mm, depth {cbore['counterbore_depth_mm']:g} mm"
            )

    return OperationGraph(
        schema_version="0.2",
        part_family="followup_feature_v0",
        part_name="corner_holes",
        reasoning="Deterministic follow-up: corner hole coordinates from active part bounding_box_mm.",
        assumptions=assumptions,
        operations=[
            {
                "id": "h1",
                "type": "hole_wizard",
                "face_of": "active_top_face",
                "hole_type": hole_type,
                "fastener_size": fastener,
                "through_all": True,
                "depth_mm": 0.0,
                "positions": positions,
            },
            {"id": "rb1", "type": "rebuild"},
        ],
    )


def _try_edge_finish(prompt: str) -> OperationGraph | None:
    text = prompt.lower()
    is_chamfer = "chamfer" in text
    is_fillet = "fillet" in text
    if not is_chamfer and not is_fillet:
        return None

    # Compound prompt with a NEW shape keyword? Stand down — the shape pattern
    # is responsible for the entire request, including any compound fillet
    # or chamfer clause.
    if any(re.search(rf"\b{kw}\b", text) for kw in _NEW_SHAPE_KEYWORDS):
        return None

    distance = _first_distance(prompt)
    if distance is None:
        name = "chamfer" if is_chamfer else "fillet"
        return _needs_input(name, f"{name} size in mm")

    top_edges = "top" in text
    edge_selector = ["__top_edges__"] if top_edges else []
    scope = "top edges" if top_edges else "all external edges"

    if is_chamfer:
        return OperationGraph(
            schema_version="0.2",
            part_family="followup_feature_v0",
            part_name="chamfer",
            reasoning=f"Deterministic follow-up: apply {distance:g} mm chamfer to {scope}.",
            assumptions=[f"Apply chamfer to {scope} of the active part"],
            operations=[
                {
                    "id": "ch1",
                    "type": "chamfer",
                    "feature_ids": edge_selector,
                    "distance_mm": distance,
                },
                {"id": "rb1", "type": "rebuild"},
            ],
        )

    return OperationGraph(
        schema_version="0.2",
        part_family="followup_feature_v0",
        part_name="fillet",
        reasoning=f"Deterministic follow-up: apply R{distance:g} mm fillet to {scope}.",
        assumptions=[f"Apply fillet to {scope} of the active part"],
        operations=[
            {
                "id": "fi1",
                "type": "fillet",
                "feature_ids": edge_selector,
                "radius_mm": distance,
            },
            {"id": "rb1", "type": "rebuild"},
        ],
    )


def _needs_input(part_name: str, missing: str) -> OperationGraph:
    return OperationGraph(
        schema_version="0.2",
        part_family="followup_feature_v0",
        part_name=part_name,
        missing_inputs=[missing],
        operations=[{"id": "noop1", "type": "noop", "message": f"Need: {missing}"}],
    )


def _fastener_size(prompt: str) -> str:
    match = _FASTENER.search(prompt)
    return f"M{match.group(1)}".upper() if match else "M6"


def _hole_type(prompt: str) -> str:
    text = prompt.lower()
    if "counterbore" in text or "counterbored" in text:
        return "counterbore"
    if "countersink" in text or "countersunk" in text:
        return "countersink"
    if "tap" in text or "tapped" in text:
        return "tapped"
    return "simple"


def _explicit_inset(prompt: str) -> float | None:
    match = _EXPLICIT_INSET.search(prompt)
    return float(match.group(1)) if match else None


def _first_distance(prompt: str) -> float | None:
    match = _DISTANCE.search(prompt)
    return float(match.group(1)) if match else None


def _default_inset(fastener: str) -> float:
    row = resolve_edge_inset(fastener)
    return float(row["inset_mm"]) if row else 10.0


def _hole_outer_diameter(fastener: str, hole_type: str) -> float:
    if hole_type == "counterbore":
        row = resolve_counterbore(fastener)
        if row:
            return float(row["counterbore_diameter_mm"])

    row = resolve_clearance_hole(fastener)
    return float(row["diameter_mm"]) if row else 6.6
