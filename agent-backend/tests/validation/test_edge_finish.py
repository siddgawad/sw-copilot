"""Tests for FilletHandler and ChamferHandler."""
from __future__ import annotations

import pytest

from models.schemas import (
    AddCenterRectangleOp,
    ChamferOp,
    CreatePartOp,
    CreateSketchOp,
    ExtrudeBossOp,
    FilletOp,
    OperationGraph,
)
from validation import Build123dBackend


def _plate_graph(extra_ops: list) -> OperationGraph:
    return OperationGraph(operations=[
        CreatePartOp(id="p1"),
        CreateSketchOp(id="sk1", plane="Front Plane", sketch_id="sk1"),
        AddCenterRectangleOp(id="r1", sketch_id="sk1", length=100.0, width=60.0),
        ExtrudeBossOp(id="e1", profile_id="sk1", depth_mm=10.0),
        *extra_ops,
    ])


def test_fillet_all_edges_2mm_preserves_bbox_within_tolerance():
    """A 2mm fillet on a 100×60×10 plate shrinks bbox by at most ~0.6mm in
    each corner (1 - 1/sqrt(2)) × 2mm. Bbox extents stay ~100×60×10."""
    result = Build123dBackend().execute(_plate_graph([
        FilletOp(id="fi1", feature_ids=[], radius_mm=2.0),
    ]))
    assert result.success, result.errors
    bb = result.bounding_box_mm
    assert bb.x_mm == pytest.approx(100.0, abs=0.05)
    assert bb.y_mm == pytest.approx(60.0, abs=0.05)
    assert bb.z_mm == pytest.approx(10.0, abs=0.05)


def test_fillet_radius_too_large_records_error():
    """Fillet of R=10 on a 10mm-thick plate → ValueError → recorded as error."""
    result = Build123dBackend().execute(_plate_graph([
        FilletOp(id="fi1", feature_ids=[], radius_mm=10.0),
    ]))
    assert not result.success
    assert any("radius" in e.lower() or "ValueError" in e for e in result.errors)


def test_chamfer_top_edges_2mm_preserves_overall_bbox():
    result = Build123dBackend().execute(_plate_graph([
        ChamferOp(id="ch1", feature_ids=["__top_edges__"], distance_mm=2.0),
    ]))
    assert result.success, result.errors
    bb = result.bounding_box_mm
    assert bb.x_mm == pytest.approx(100.0, abs=0.05)
    assert bb.y_mm == pytest.approx(60.0, abs=0.05)
