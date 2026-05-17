"""Tests for deterministic box, cylinder, and help fast-path parsers."""
import pytest
from agents.box_v0 import match as box_match, try_generate as box_try
from agents.cylinder_v0 import match as cyl_match, try_generate as cyl_try
from agents.help_v0 import match as help_match, try_generate as help_try
from models.schemas import BoundingBox, DocumentContext
from patterns.followup_features import try_generate as followup_try


# ── help_v0 ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("prompt", [
    "hi", "hello", "hey", "what can you do", "help",
    "what do you do", "what are your capabilities", "getting started",
])
def test_help_match(prompt):
    assert help_match(prompt), f"Should match: {prompt!r}"


@pytest.mark.parametrize("prompt", [
    "create a box", "50mm shaft", "add holes",
])
def test_help_no_match(prompt):
    assert not help_match(prompt), f"Should not match: {prompt!r}"


def test_help_graph_is_noop():
    graph = help_try("hi")
    assert graph is not None
    assert len(graph.operations) == 1
    assert graph.operations[0].type == "noop"
    assert "box" in graph.operations[0].message.lower()


# ── box_v0 matching ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("prompt,expected", [
    ("50mm wide 30mm deep 20mm tall box",        (50, 30, 20)),
    ("100x60x40mm block",                         (100, 60, 40)),
    ("create a 50mm x 40mm x 30mm box",           (50, 40, 30)),
    ("create a 50 mm x 40 mm x 30 mm box",        (50, 40, 30)),
    ("50 by 30 by 20 rectangular block",          (50, 30, 20)),
    ("50mm by 30mm by 20mm rectangular block",    (50, 30, 20)),
    ("create a 80mm wide 40mm deep 25mm tall box", (80, 40, 25)),
    ("200mm wide 100mm deep 50mm tall rectangular block", (200, 100, 50)),
])
def test_box_match(prompt, expected):
    result = box_match(prompt)
    assert result is not None, f"Expected match for: {prompt!r}"
    assert tuple(result) == pytest.approx(expected)


@pytest.mark.parametrize("prompt", [
    "create a cylinder 40mm diameter 100mm long",
    "just a random part",
    "shaft 20mm radius",
    "export to PDF",
])
def test_box_no_match(prompt):
    assert box_match(prompt) is None, f"Should not match: {prompt!r}"


def test_box_graph_structure():
    graph = box_try("100x60x40mm block")
    assert graph is not None
    assert graph.part_family == "box_v0"
    types = [op.type for op in graph.operations]
    assert "create_part" in types
    assert "create_sketch" in types
    assert "add_center_rectangle" in types
    assert "extrude_boss" in types
    assert "rebuild" in types


def test_box_graph_dimensions():
    graph = box_try("50mm wide 30mm deep 20mm tall box")
    assert graph is not None
    rect_op = next(op for op in graph.operations if op.type == "add_center_rectangle")
    extrude_op = next(op for op in graph.operations if op.type == "extrude_boss")
    assert rect_op.length == pytest.approx(50)
    assert rect_op.width == pytest.approx(30)
    assert extrude_op.depth_mm == pytest.approx(20)


# ── cylinder_v0 matching ───────────────────────────────────────────────────────

@pytest.mark.parametrize("prompt,expected_r,expected_l", [
    ("40mm diameter shaft 100mm long",         20.0, 100.0),
    ("cylinder 30mm radius 50mm tall",         30.0, 50.0),
    ("30mm circle extruded 60mm",              15.0, 60.0),
    ("create a 20mm diameter pin 45mm long",   10.0, 45.0),
    ("60mm diameter rod 200mm length",         30.0, 200.0),
])
def test_cyl_match(prompt, expected_r, expected_l):
    result = cyl_match(prompt)
    assert result is not None, f"Expected match for: {prompt!r}"
    r, l = result
    assert r == pytest.approx(expected_r)
    assert l == pytest.approx(expected_l)


@pytest.mark.parametrize("prompt", [
    "50mm wide 30mm deep 20mm tall box",
    "update title block revision C",
    "export all drawings to PDF",
])
def test_cyl_no_match(prompt):
    assert cyl_match(prompt) is None, f"Should not match: {prompt!r}"


def test_cyl_graph_structure():
    graph = cyl_try("40mm diameter shaft 100mm long")
    assert graph is not None
    assert graph.part_family == "cylinder_v0"
    types = [op.type for op in graph.operations]
    assert "create_part" in types
    assert "create_sketch" in types
    assert "add_circles" in types
    assert "extrude_boss" in types


def test_cyl_graph_dimensions():
    graph = cyl_try("60mm diameter rod 200mm length")
    assert graph is not None
    circle_op = next(op for op in graph.operations if op.type == "add_circles")
    extrude_op = next(op for op in graph.operations if op.type == "extrude_boss")
    assert circle_op.circles[0].diameter == pytest.approx(60.0)
    assert extrude_op.depth_mm == pytest.approx(200.0)


# ── follow-up feature matching ────────────────────────────────────────────────

def test_followup_corner_counterbore_uses_active_bbox():
    ctx = DocumentContext(
        document_type="Part",
        body_count=1,
        bounding_box_mm=BoundingBox(x_mm=50, y_mm=40, z_mm=30),
    )

    graph = followup_try("add four M6 counterbore holes at the corners", ctx)

    assert graph is not None
    assert graph.part_family == "followup_feature_v0"
    hole_op = next(op for op in graph.operations if op.type == "hole_wizard")
    assert hole_op.face_of == "active_top_face"
    assert hole_op.fastener_size == "M6"
    assert hole_op.hole_type == "counterbore"
    assert [(p.x_mm, p.y_mm) for p in hole_op.positions] == pytest.approx([
        (-15, -10),
        (15, -10),
        (-15, 10),
        (15, 10),
    ])


def test_followup_corner_holes_without_bbox_needs_context_not_llm():
    graph = followup_try("add four M6 counterbore holes at the corners", DocumentContext(document_type="Part"))

    assert graph is not None
    assert graph.missing_inputs
    assert graph.operations[0].type == "noop"


def test_followup_top_chamfer_selects_top_edges():
    graph = followup_try("add a 3mm chamfer on the top edges", DocumentContext(document_type="Part"))

    assert graph is not None
    assert graph.part_family == "followup_feature_v0"
    chamfer = next(op for op in graph.operations if op.type == "chamfer")
    assert chamfer.distance_mm == pytest.approx(3.0)
    assert chamfer.feature_ids == ["__top_edges__"]
