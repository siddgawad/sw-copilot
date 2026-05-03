# Regression tests for the post-execution validation agent. The agent compares
# the requested OperationGraph against the PartReport returned by Codex's
# ExtractPartReport so that the runtime can flag silent geometric drift before
# the user notices.

from __future__ import annotations

import pytest

from agents.validation_agent import validate
from models.schemas import (
    BoundingBox,
    CircleEntity,
    ExtrudeBossOp,
    OperationGraph,
    PartFeatureInfo,
    PartReport,
    RectangleEntity,
    SketchOp,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _box_graph(width: float = 50, depth: float = 30, height: float = 20) -> OperationGraph:
    """Build a canonical box graph: rectangle on Top Plane, extruded by `height`."""
    return OperationGraph(
        operations=[
            SketchOp(
                id="sk1",
                plane="Top Plane",
                entities=[RectangleEntity(
                    x1_mm=-width / 2, y1_mm=-depth / 2,
                    x2_mm=width / 2,  y2_mm=depth / 2,
                )],
            ),
            ExtrudeBossOp(id="f1", profile_id="sk1", depth_mm=height),
        ],
    )


def _shaft_graph(diameter: float = 40, length: float = 100) -> OperationGraph:
    """Cylinder on Front Plane (extruded along Y)."""
    return OperationGraph(
        operations=[
            SketchOp(
                id="sk1",
                plane="Front Plane",
                entities=[CircleEntity(cx_mm=0, cy_mm=0, radius_mm=diameter / 2)],
            ),
            ExtrudeBossOp(id="f1", profile_id="sk1", depth_mm=length),
        ],
    )


def _good_box_report(width=50, depth=30, height=20) -> PartReport:
    return PartReport(
        body_count=1,
        bounding_box=BoundingBox(x_mm=width, y_mm=depth, z_mm=height),
        mass_g=234.0,
        feature_count=1,
        features=[PartFeatureInfo(name="Boss-Extrude1", type="Extrusion")],
    )


# ── Happy path ────────────────────────────────────────────────────────────────

def test_box_request_matches_box_report():
    report = validate(_box_graph(), _good_box_report())
    assert report.passed is True
    assert report.has_warnings is False
    assert report.discrepancies == []
    assert report.expected_summary["bounding_box"] == {
        "x_mm": 50.0, "y_mm": 30.0, "z_mm": 20.0,
    }


def test_shaft_request_matches_shaft_report():
    """Front-plane extrude: depth maps to Y axis, not Z."""
    graph  = _shaft_graph(diameter=40, length=100)
    report = PartReport(
        body_count=1,
        bounding_box=BoundingBox(x_mm=40, y_mm=100, z_mm=40),
        feature_count=1,
        features=[PartFeatureInfo(name="Shaft", type="Extrusion")],
    )
    result = validate(graph, report)
    assert result.passed is True


def test_within_tolerance_passes():
    """SW often returns bbox values fractionally off from request — tolerance covers that."""
    report = _good_box_report(width=50.4, depth=29.7, height=20.2)
    result = validate(_box_graph(), report, tolerance_mm=1.0)
    assert result.passed is True
    assert result.discrepancies == []


# ── Bounding-box failures ─────────────────────────────────────────────────────

def test_wrong_height_flagged_as_error():
    report = _good_box_report(height=40)
    result = validate(_box_graph(), report)
    assert result.passed is False
    assert any(d.category == "bounding_box" and d.severity == "error" for d in result.discrepancies)


def test_missing_bbox_flagged_as_warning_not_error():
    report = PartReport(body_count=1, bounding_box=None, feature_count=1)
    result = validate(_box_graph(), report)
    assert result.passed is True  # warnings only
    assert result.has_warnings is True
    assert any(d.category == "bounding_box" and d.severity == "warning" for d in result.discrepancies)


# ── Body-count checks ─────────────────────────────────────────────────────────

def test_zero_bodies_is_error():
    report = PartReport(
        body_count=0, bounding_box=None, feature_count=0, features=[],
    )
    result = validate(_box_graph(), report)
    assert result.passed is False
    body_errs = [d for d in result.discrepancies if d.category == "body_count"]
    assert body_errs and body_errs[0].severity == "error"


def test_sketch_only_graph_allows_zero_bodies():
    graph = OperationGraph(
        operations=[
            SketchOp(
                id="sk1",
                plane="Top Plane",
                entities=[CircleEntity(cx_mm=0, cy_mm=0, radius_mm=15)],
            ),
        ],
    )
    report = PartReport(
        body_count=0,
        bounding_box=None,
        feature_count=1,
        features=[PartFeatureInfo(name="Sketch1", type="ProfileFeature")],
    )

    result = validate(graph, report)

    assert result.passed is True
    assert not any(d.category == "body_count" for d in result.discrepancies)


def test_multiple_bodies_is_warning_only():
    report = PartReport(
        body_count=2,
        bounding_box=BoundingBox(x_mm=50, y_mm=30, z_mm=20),
        feature_count=2,
    )
    result = validate(_box_graph(), report)
    body_warns = [d for d in result.discrepancies if d.category == "body_count"]
    assert body_warns and body_warns[0].severity == "warning"
    assert result.passed is True  # still passes — just warned


# ── Feature-count checks ──────────────────────────────────────────────────────

def test_too_few_features_is_error():
    """Asked for box + 4 holes but report shows zero features."""
    graph = OperationGraph(
        operations=[
            SketchOp(id="sk1", plane="Top Plane", entities=[
                RectangleEntity(x1_mm=-25, y1_mm=-15, x2_mm=25, y2_mm=15),
            ]),
            ExtrudeBossOp(id="f1", profile_id="sk1", depth_mm=10),
        ],
    )
    report = PartReport(body_count=1, feature_count=0, features=[])
    result = validate(graph, report)
    feat_errs = [d for d in result.discrepancies if d.category == "feature_count"]
    assert feat_errs and feat_errs[0].severity == "error"


def test_extra_features_does_not_fail():
    """SW often inserts auxiliary features (origin, default planes). Don't flag those."""
    report = PartReport(
        body_count=1,
        bounding_box=BoundingBox(x_mm=50, y_mm=30, z_mm=20),
        feature_count=20,  # way more than expected
    )
    result = validate(_box_graph(), report)
    assert result.passed is True


# ── Suppressed features ───────────────────────────────────────────────────────

def test_suppressed_feature_emits_warning():
    report = PartReport(
        body_count=1,
        bounding_box=BoundingBox(x_mm=50, y_mm=30, z_mm=20),
        feature_count=2,
        features=[
            PartFeatureInfo(name="Boss-Extrude1", type="Extrusion", suppressed=False),
            PartFeatureInfo(name="Hole1", type="HoleWzd", suppressed=True),
        ],
    )
    result = validate(_box_graph(), report)
    assert result.has_warnings is True
    susp = [d for d in result.discrepancies if d.category == "suppressed_feature"]
    assert susp and "Hole1" in susp[0].actual


# ── Graphs the agent cannot derive ────────────────────────────────────────────

def test_complex_graph_skips_bbox_check_safely():
    """Multiple extrudes — agent should NOT make stuff up; it skips the bbox check."""
    graph = OperationGraph(
        operations=[
            SketchOp(id="sk1", plane="Top Plane", entities=[
                RectangleEntity(x1_mm=-25, y1_mm=-15, x2_mm=25, y2_mm=15),
            ]),
            ExtrudeBossOp(id="f1", profile_id="sk1", depth_mm=20),
            SketchOp(id="sk2", plane="f1 top", entities=[
                CircleEntity(cx_mm=0, cy_mm=0, radius_mm=5),
            ]),
            ExtrudeBossOp(id="f2", profile_id="sk2", depth_mm=15),
        ],
    )
    report = PartReport(
        body_count=1,
        bounding_box=BoundingBox(x_mm=50, y_mm=30, z_mm=35),
        feature_count=2,
    )
    result = validate(graph, report)
    # No bbox discrepancy — we can't derive the union bbox safely, so we don't try.
    assert not any(d.category == "bounding_box" for d in result.discrepancies)
    assert result.passed is True


def test_noop_only_graph_does_not_explode():
    from models.schemas import NoopOp
    graph = OperationGraph(
        operations=[NoopOp(id="n1", message="needs more info")],
    )
    report = PartReport(body_count=0, feature_count=0)
    result = validate(graph, report)
    assert result.passed is True
    assert not result.discrepancies


# ── Tolerance sweep ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("delta_mm,passes", [
    (0.0,  True),
    (0.5,  True),
    (1.0,  True),
    (1.01, False),
    (5.0,  False),
])
def test_bbox_tolerance_boundary(delta_mm, passes):
    report = _good_box_report(height=20 + delta_mm)
    result = validate(_box_graph(), report, tolerance_mm=1.0)
    assert result.passed is passes
