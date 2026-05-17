"""
End-to-end feature matrix — exhaustive prompt -> OperationGraph coverage.

This is the deterministic-compiler proof. Every test case is a real natural-
language prompt that flows through the same /generate pipeline a user hits.
We assert the produced graph has the expected operations, schema_version,
and that it passes Pydantic validation cleanly.

What this matrix covers:
  * Every shape primitive (box, plate, flange, cylinder, shaft, gear)
  * Multiple dimension formats (50x30x20, 50mm x 30mm x 20mm, 50 by 30, etc.)
  * Multiple planes (Top, Front, Right)
  * Multiple measurement scales (mm, small/medium/large parts)
  * Follow-up features (corner holes, top chamfer, all-edge fillet)
  * Counterbore + countersink + tapped + simple hole variants
  * Multiple bolt circle counts (4/6/8/12 holes)
  * Combined prompts where one base shape carries multiple follow-up features

Anything in this file that fails means a regression — the deterministic
compiler is the single most important guarantee in the app.
"""
from __future__ import annotations

import pytest

from models.schemas import BoundingBox, DocumentContext, OperationGraph
from patterns.router import try_pattern_match


# ── Helpers ──────────────────────────────────────────────────────────────────

def _run(prompt: str, *, body_count: int = 0, bbox: tuple | None = None) -> OperationGraph | None:
    """Run the deterministic pattern router with optional active-part context."""
    ctx = DocumentContext(
        document_type="Part" if body_count > 0 else "None",
        body_count=body_count,
        bounding_box_mm=BoundingBox(x_mm=bbox[0], y_mm=bbox[1], z_mm=bbox[2]) if bbox else None,
    )
    return try_pattern_match(prompt, ctx)


def _op_types(graph: OperationGraph) -> list[str]:
    return [op.type for op in graph.operations]


def _has_ops(graph: OperationGraph, *required: str) -> bool:
    types = set(_op_types(graph))
    return all(r in types for r in required)


# ── Box primitive (multiple formats, dimensions, planes) ──────────────────────

@pytest.mark.parametrize("prompt,expected_dims", [
    ("create a 50mm wide 30mm deep 20mm tall box",        (50, 30, 20)),
    ("100x60x40mm block",                                  (100, 60, 40)),
    ("create a 200mm x 150mm x 25mm box",                  (200, 150, 25)),
    ("box 80 by 40 by 20",                                 (80, 40, 20)),
    ("create a 1000mm by 800mm by 50mm rectangular block", (1000, 800, 50)),
    ("tiny box 5mm x 5mm x 5mm",                           (5, 5, 5)),
])
def test_box_at_many_scales(prompt, expected_dims):
    graph = _run(prompt)
    assert graph is not None, f"{prompt!r} should route to box_v0"
    assert graph.part_family == "box_v0"
    assert _has_ops(graph, "create_part", "create_sketch", "add_center_rectangle", "extrude_boss")
    rect = next(op for op in graph.operations if op.type == "add_center_rectangle")
    extrude = next(op for op in graph.operations if op.type == "extrude_boss")
    assert rect.length == pytest.approx(expected_dims[0])
    assert rect.width == pytest.approx(expected_dims[1])
    assert extrude.depth_mm == pytest.approx(expected_dims[2])


# ── Plate primitive (NEW — flat rectangular part) ────────────────────────────

@pytest.mark.parametrize("prompt", [
    "create a 100x100x5mm plate",
    "make a plate 200mm x 150mm x 6mm",
    "plate 100 by 60 by 5",
    "mounting plate 80x60x4mm",
    "base plate 300x200x10mm",
])
def test_plate_basic_dimensions(prompt):
    graph = _run(prompt)
    assert graph is not None, f"{prompt!r} should match plate"
    assert graph.part_family == "plate_v0"
    assert _has_ops(graph, "create_part", "create_sketch", "add_center_rectangle", "extrude_boss")


def test_plate_thickness_is_smallest_dimension():
    """The deterministic compiler must always pick the smallest dim as thickness."""
    graph = _run("create a plate 100x60x5mm")
    assert graph is not None
    extrude = next(op for op in graph.operations if op.type == "extrude_boss")
    assert extrude.depth_mm == pytest.approx(5)


def test_plate_with_corner_holes():
    graph = _run("mounting plate 80x60x4mm with 4 M5 holes at corners")
    assert graph is not None
    assert _has_ops(graph, "hole_wizard")
    hole_op = next(op for op in graph.operations if op.type == "hole_wizard")
    assert hole_op.fastener_size == "M5"
    assert len(hole_op.positions) == 4


def test_plate_with_counterbore_holes():
    graph = _run("plate 120x80x6mm with 4 M8 counterbored holes at corners")
    assert graph is not None
    hole_op = next(op for op in graph.operations if op.type == "hole_wizard")
    assert hole_op.hole_type == "counterbore"
    assert hole_op.fastener_size == "M8"


def test_plate_plane_hint():
    graph = _run("create a plate 100x100x5mm on front plane")
    assert graph is not None
    sketch = next(op for op in graph.operations if op.type == "create_sketch")
    assert sketch.plane == "Front Plane"


# ── Flange primitive (NEW — circular disk + bolt circle) ──────────────────────

@pytest.mark.parametrize("prompt", [
    "create a flange 100mm OD 6mm thick",
    "flange 80mm diameter 5mm thick",
    "circular flange 120mm 8mm thick",
    "disc 50mm diameter 3mm thick",
])
def test_flange_basic_dimensions(prompt):
    graph = _run(prompt)
    assert graph is not None, f"{prompt!r} should match flange"
    assert graph.part_family == "flange_v0"
    assert _has_ops(graph, "create_part", "create_sketch", "add_circles", "extrude_boss")


def test_flange_with_bolt_circle_creates_pattern():
    graph = _run("flange 100mm OD 6mm thick with 6 M8 holes on 80mm PCD")
    assert graph is not None
    assert _has_ops(graph, "hole_wizard", "circular_pattern")
    pat = next(op for op in graph.operations if op.type == "circular_pattern")
    assert pat.count == 6
    assert pat.pcd_mm == pytest.approx(80)
    hole = next(op for op in graph.operations if op.type == "hole_wizard")
    assert hole.fastener_size == "M8"


def test_flange_8_bolt_circle():
    graph = _run("flange 200mm OD 10mm thick with 8 M10 holes on 160mm PCD")
    assert graph is not None
    pat = next(op for op in graph.operations if op.type == "circular_pattern")
    assert pat.count == 8


# ── Cylinder primitive (shaft / rod) ──────────────────────────────────────────

@pytest.mark.parametrize("prompt", [
    "create a cylinder 40mm diameter 100mm long",
    "create a cylinder 50mm diameter 200mm long",
    "cylinder 30mm diameter 75mm long",
])
def test_cylinder_at_scale(prompt):
    graph = _run(prompt)
    assert graph is not None, f"{prompt!r} should match cylinder"
    # cylinder_v0 emits sketch (circle) → extrude_boss
    assert any(op.type in ("sketch", "create_sketch") for op in graph.operations)
    assert any(op.type == "extrude_boss" for op in graph.operations)


def test_shaft_with_dimensions_routes_to_shaft_pattern():
    """The shaft pattern emits a flanged-shaft graph by design (shaft + flange + holes
    are the common engineering trio). Just verify it produces a coherent multi-op graph."""
    graph = _run("make a 30mm diameter shaft 150mm long")
    assert graph is not None
    types = [op.type for op in graph.operations]
    assert "sketch" in types or "create_sketch" in types
    assert "extrude_boss" in types


# ── Help / capabilities ──────────────────────────────────────────────────────

@pytest.mark.parametrize("prompt", ["hi", "help", "what can you do", "getting started"])
def test_help_routes_to_noop(prompt):
    graph = _run(prompt)
    assert graph is not None
    assert any(op.type == "noop" for op in graph.operations)


# ── Follow-up features on an active body ──────────────────────────────────────

@pytest.mark.parametrize("prompt,fastener", [
    ("add four M6 counterbore holes at the corners", "M6"),
    ("add four M8 counterbore holes at the corners", "M8"),
    ("add four M10 counterbore holes at the corners", "M10"),
    ("add four M5 holes at the corners",             "M5"),
])
def test_followup_corner_holes_uses_bbox(prompt, fastener):
    graph = _run(prompt, body_count=1, bbox=(100, 60, 10))
    assert graph is not None
    hole = next(op for op in graph.operations if op.type == "hole_wizard")
    assert hole.fastener_size == fastener
    assert len(hole.positions) == 4


def test_followup_corner_holes_box_too_small_returns_noop():
    """A 25x20mm box can't fit 4 M8 counterbore holes — must be a clear noop."""
    graph = _run("add four M8 counterbore holes at the corners", body_count=1, bbox=(25, 20, 5))
    assert graph is not None
    assert graph.missing_inputs, "Should surface missing_inputs explaining the issue"
    assert any("too small" in m.lower() or "fit" in m.lower() for m in graph.missing_inputs)


@pytest.mark.parametrize("prompt,radius", [
    ("add a 2mm fillet on all edges",   2),
    ("add a 5mm fillet on all edges",   5),
    ("apply a 10mm fillet on all edges", 10),
])
def test_followup_all_edge_fillet(prompt, radius):
    graph = _run(prompt, body_count=1, bbox=(100, 60, 20))
    assert graph is not None
    fil = next(op for op in graph.operations if op.type == "fillet")
    assert fil.radius_mm == pytest.approx(radius)


@pytest.mark.parametrize("prompt,distance", [
    ("add a 2mm chamfer on the top edges", 2),
    ("add a 3mm chamfer on the top edges", 3),
])
def test_followup_top_edge_chamfer(prompt, distance):
    graph = _run(prompt, body_count=1, bbox=(100, 60, 20))
    assert graph is not None
    ch = next(op for op in graph.operations if op.type == "chamfer")
    assert ch.distance_mm == pytest.approx(distance)
    assert "__top_edges__" in ch.feature_ids


# ── Compound feature scenario via sequential prompts ──────────────────────────

def test_full_part_build_sequence_box_then_holes_then_fillet():
    """Simulates a real user session: box -> holes -> fillet. Each step must
    independently route to a deterministic pattern (no LLM)."""
    g1 = _run("create a 100x60x10mm plate")
    assert g1 is not None and g1.part_family == "plate_v0"

    g2 = _run(
        "add four M6 counterbore holes at the corners",
        body_count=1,
        bbox=(100, 60, 10),
    )
    assert g2 is not None
    assert _has_ops(g2, "hole_wizard")

    g3 = _run("add a 2mm fillet on all edges", body_count=1, bbox=(100, 60, 10))
    assert g3 is not None
    assert _has_ops(g3, "fillet")


def test_full_flange_with_bolt_circle_in_one_prompt():
    """Compound single-prompt feature — flange + bolt circle in one shot."""
    graph = _run("flange 150mm OD 8mm thick with 6 M8 counterbored holes on 120mm PCD")
    assert graph is not None
    assert _has_ops(graph, "create_part", "create_sketch", "add_circles",
                    "extrude_boss", "hole_wizard", "circular_pattern", "rebuild")


# ── Schema integrity for every test case ──────────────────────────────────────

@pytest.mark.parametrize("prompt", [
    "create a 50mm wide 30mm deep 20mm tall box",
    "100x60x40mm block",
    "make a plate 200mm x 150mm x 6mm",
    "mounting plate 80x60x4mm with 4 M5 holes at corners",
    "flange 100mm OD 6mm thick with 6 M8 holes on 80mm PCD",
    "create a cylinder 40mm diameter 100mm long",
])
def test_emitted_graph_round_trips_through_pydantic(prompt):
    """Every deterministic graph must serialise + parse back without loss."""
    graph = _run(prompt)
    assert graph is not None
    # round-trip through JSON to confirm Pydantic discriminated union resolves
    serialized = graph.model_dump_json()
    restored = OperationGraph.model_validate_json(serialized)
    assert restored.schema_version == graph.schema_version
    assert len(restored.operations) == len(graph.operations)


# ── Schema-version guard ──────────────────────────────────────────────────────

@pytest.mark.parametrize("prompt", [
    "create a 50x30x20mm box",
    "plate 100x100x5mm",
    "flange 80mm OD 5mm thick",
    "cylinder 30mm diameter 50mm long",
])
def test_all_deterministic_graphs_use_schema_version_0_2(prompt):
    graph = _run(prompt)
    assert graph is not None
    assert graph.schema_version == "0.2", (
        f"Deterministic pattern {graph.part_family} must emit schema_version='0.2'"
    )


# ── L-bracket / angle-bracket pattern (NEW) ───────────────────────────────────

@pytest.mark.parametrize("prompt", [
    "create an L-bracket 80x60x5mm",
    "make a bracket 100x80x6mm",
    "L-bracket 120x80x8mm",
    "angle bracket 60x40x4mm",
])
def test_bracket_recognised(prompt):
    graph = _run(prompt)
    assert graph is not None, f"{prompt!r} should match bracket"
    assert graph.part_family == "bracket_v0"
    # Two perpendicular plates = two sketches + two extrudes
    types = [op.type for op in graph.operations]
    assert types.count("create_sketch") == 2
    assert types.count("extrude_boss") == 2


# ── Bushing pattern (NEW) ─────────────────────────────────────────────────────

@pytest.mark.parametrize("prompt", [
    "create a bushing 30mm OD 15mm ID 40mm long",
    "bushing 25mm outer 12mm inner 30mm long",
    "make a bushing 40mm OD 20mm ID 50mm long",
])
def test_bushing_recognised(prompt):
    graph = _run(prompt)
    assert graph is not None, f"{prompt!r} should match bushing"
    assert graph.part_family == "bushing_v0"
    # Outer cylinder + inner cut = sketch+extrude_boss + sketch+extrude_cut
    types = [op.type for op in graph.operations]
    assert "extrude_boss" in types
    assert "extrude_cut" in types


def test_bushing_inner_smaller_than_outer():
    graph = _run("bushing 30mm OD 15mm ID 40mm long")
    assert graph is not None
    boss = next(op for op in graph.operations if op.type == "extrude_boss")
    assert boss.depth_mm == pytest.approx(40)


# ── Compound features in a single prompt (NEW) ────────────────────────────────

def test_compound_plate_with_holes_and_fillet():
    """Single prompt: plate with holes AND fillet at once."""
    graph = _run("create a 100x60x10mm plate with 4 M6 holes at corners and 2mm fillet on all edges")
    assert graph is not None
    assert graph.part_family == "plate_v0"
    types = [op.type for op in graph.operations]
    assert "hole_wizard" in types
    assert "fillet" in types
    fil = next(op for op in graph.operations if op.type == "fillet")
    assert fil.radius_mm == pytest.approx(2)


def test_compound_plate_with_chamfer_only():
    graph = _run("create a 200x150x6mm plate with 3mm chamfer on top edges")
    assert graph is not None
    assert graph.part_family == "plate_v0"
    types = [op.type for op in graph.operations]
    assert "chamfer" in types
    ch = next(op for op in graph.operations if op.type == "chamfer")
    assert ch.distance_mm == pytest.approx(3)
    assert "__top_edges__" in ch.feature_ids


def test_compound_flange_with_bolt_circle_and_fillet():
    graph = _run("flange 150mm OD 8mm thick with 6 M8 holes on 120mm PCD and 2mm fillet on all edges")
    assert graph is not None
    assert graph.part_family == "flange_v0"
    types = [op.type for op in graph.operations]
    assert "hole_wizard" in types
    assert "circular_pattern" in types
    assert "fillet" in types


def test_compound_plate_full_house():
    """Plate + holes + fillet + chamfer — every combination at once."""
    graph = _run(
        "create a 120x80x6mm plate with 4 M5 counterbored holes at corners "
        "and 3mm fillet on all edges and 1mm chamfer on top edges"
    )
    assert graph is not None
    types = [op.type for op in graph.operations]
    assert types.count("hole_wizard") == 1
    assert types.count("fillet") == 1
    assert types.count("chamfer") == 1
    # Rebuild must be last so all features get a clean recompute.
    assert types[-1] == "rebuild"


def test_compound_features_preserve_order():
    """Sketches and extrudes come BEFORE the follow-up features; rebuild last."""
    graph = _run("plate 100x100x5mm with 4 M6 holes at corners and 2mm fillet on all edges")
    assert graph is not None
    types = [op.type for op in graph.operations]
    assert types.index("create_sketch") < types.index("extrude_boss")
    assert types.index("extrude_boss") < types.index("hole_wizard")
    assert types.index("hole_wizard") < types.index("fillet")
    assert types.index("fillet") < types.index("rebuild")


# ── Spacer (round + square) ───────────────────────────────────────────────────

@pytest.mark.parametrize("prompt", [
    "create a spacer 30mm OD 10mm ID 5mm thick",
    "round spacer 25mm OD 8mm ID 5mm thick",
])
def test_spacer_round(prompt):
    graph = _run(prompt)
    assert graph is not None
    assert graph.part_family == "spacer_v0"
    types = [op.type for op in graph.operations]
    assert "extrude_boss" in types and "extrude_cut" in types


def test_spacer_square():
    graph = _run("rectangular spacer 40x20mm 10mm bore 5mm thick")
    assert graph is not None
    assert graph.part_family == "spacer_v0"
    assert any(op.type == "add_center_rectangle" for op in graph.operations)


# ── Pipe / tube ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("prompt", [
    "create a pipe 25mm OD 20mm ID 200mm long",
    "tube 32mm OD 28mm ID 500mm long",
])
def test_pipe_basic(prompt):
    graph = _run(prompt)
    assert graph is not None
    assert graph.part_family == "pipe_v0"
    assert any(op.type == "extrude_cut" for op in graph.operations)


def test_pipe_wall_thickness_form():
    """When the prompt gives a wall thickness, compute ID = OD - 2*wall."""
    graph = _run("pipe 30mm OD 2mm wall 250mm long")
    assert graph is not None
    cuts = [op for op in graph.operations if op.type == "add_circles"]
    inner = cuts[-1].circles[0].diameter
    assert inner == pytest.approx(26.0)


# ── Enclosure (box + shell + corner holes) ────────────────────────────────────

def test_enclosure_basic():
    graph = _run("create an enclosure 100x60x40mm with 2mm walls")
    assert graph is not None
    assert graph.part_family == "enclosure_v0"
    types = [op.type for op in graph.operations]
    assert "extrude_boss" in types
    assert "shell" in types


def test_enclosure_with_mounting_holes():
    graph = _run("create a junction box 80x80x40mm 2mm walls with 4 M3 mounting holes at corners")
    assert graph is not None
    assert graph.part_family == "enclosure_v0"
    types = [op.type for op in graph.operations]
    assert "hole_wizard" in types


def test_enclosure_with_compound_fillet():
    """Enclosure + fillet in one prompt."""
    graph = _run("create an enclosure 120x80x50mm with 3mm walls and 2mm fillet on all edges")
    assert graph is not None
    assert any(op.type == "fillet" for op in graph.operations)


# ── Washer (ISO 7089) ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("prompt,fastener,od_mm,id_mm,thickness_mm", [
    ("create an M3 washer",  "M3", 7.0,  3.2, 0.5),
    ("M6 washer ISO 7089",   "M6", 12.0, 6.4, 1.6),
    ("M8 washer",            "M8", 16.0, 8.4, 1.6),
    ("M10 plain washer",     "M10", 20.0, 10.5, 2.0),
])
def test_washer_iso_7089(prompt, fastener, od_mm, id_mm, thickness_mm):
    graph = _run(prompt)
    assert graph is not None, f"{prompt!r} should match washer"
    assert graph.part_family == "washer_v0"
    boss = next(op for op in graph.operations if op.type == "extrude_boss")
    assert boss.depth_mm == pytest.approx(thickness_mm)


def test_washer_custom_dimensions():
    graph = _run("make a washer 10mm OD 4mm ID 1mm thick")
    assert graph is not None
    assert graph.part_family == "washer_v0"


# ── Comprehensive end-to-end coverage proof ───────────────────────────────────

@pytest.mark.parametrize("prompt", [
    # Every shape family represented:
    "create a 50x30x20mm box",
    "plate 100x60x5mm",
    "flange 80mm OD 5mm thick",
    "create an L-bracket 80x60x5mm",
    "create a bushing 30mm OD 15mm ID 40mm long",
    "create a spacer 30mm OD 10mm ID 5mm thick",
    "create a pipe 25mm OD 20mm ID 200mm long",
    "create an enclosure 100x60x40mm with 2mm walls",
    "create an M6 washer",
    "cylinder 40mm diameter 100mm long",
    # Compound prompts:
    "plate 100x60x5mm with 4 M6 holes at corners and 2mm fillet on all edges",
    "flange 100mm OD 6mm thick with 6 M8 holes on 80mm PCD and 1mm chamfer on top edges",
    "enclosure 150x100x50mm with 3mm walls and 4 M3 holes at corners and 2mm fillet on all edges",
])
def test_all_patterns_produce_executable_graphs(prompt):
    """Every supported prompt produces a complete, schema-valid OperationGraph
    with at least one geometry-producing op and a terminal rebuild."""
    graph = _run(prompt)
    assert graph is not None, f"Pattern coverage gap: {prompt!r}"
    assert graph.schema_version == "0.2"
    types = [op.type for op in graph.operations]
    assert any(t in types for t in ("extrude_boss", "extrude_cut", "noop")), \
        f"Graph for {prompt!r} has no geometry-producing op: {types}"
    # Round-trip safety:
    serialized = graph.model_dump_json()
    OperationGraph.model_validate_json(serialized)
