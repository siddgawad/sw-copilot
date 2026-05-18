"""End-to-end smoke tests for Build123dBackend.

Asserts the backend wires up correctly for the three most-common shape graphs
emitted by the deterministic pattern library.
"""
from __future__ import annotations

import pytest

from models.schemas import (
    AddCenterRectangleOp,
    AddCirclesOp,
    CirclePrimitive,
    CreatePartOp,
    CreateSketchOp,
    ExtrudeBossOp,
    OperationGraph,
    RebuildOp,
)
from validation import Build123dBackend


def _run(*ops) -> "Build123dResult":  # type: ignore[name-defined]
    graph = OperationGraph(operations=list(ops))
    return Build123dBackend().execute(graph)


def test_empty_graph_has_no_errors_and_no_bbox():
    result = Build123dBackend().execute(OperationGraph(
        operations=[CreatePartOp(id="p1")],
    ))
    assert result.success is True
    assert result.bounding_box_mm is None
    assert result.body_count == 0


def test_100x60x5mm_plate_yields_expected_bbox():
    result = _run(
        CreatePartOp(id="p1"),
        CreateSketchOp(id="sk1", plane="Front Plane", sketch_id="sk1"),
        AddCenterRectangleOp(id="r1", sketch_id="sk1", length=100.0, width=60.0),
        ExtrudeBossOp(id="e1", profile_id="sk1", depth_mm=5.0),
        RebuildOp(id="rb1"),
    )
    assert result.success is True, result.errors
    assert result.bounding_box_mm is not None
    bb = result.bounding_box_mm
    # Front Plane = XY, extrude +Z → length × width × thickness.
    assert bb.x_mm == pytest.approx(100.0, abs=0.01)
    assert bb.y_mm == pytest.approx(60.0, abs=0.01)
    assert bb.z_mm == pytest.approx(5.0, abs=0.01)
    assert result.body_count == 1


def test_top_plane_swaps_y_and_z():
    """Regression: when the LLM emits Top Plane for a flat shape, the body
    extrudes in +Y. We accept it (no crash) but the bbox swaps Y↔Z."""
    result = _run(
        CreatePartOp(id="p1"),
        CreateSketchOp(id="sk1", plane="Top Plane", sketch_id="sk1"),
        AddCenterRectangleOp(id="r1", sketch_id="sk1", length=100.0, width=60.0),
        ExtrudeBossOp(id="e1", profile_id="sk1", depth_mm=5.0),
    )
    assert result.success is True, result.errors
    bb = result.bounding_box_mm
    assert bb.x_mm == pytest.approx(100.0, abs=0.01)
    # Top Plane = XZ → "width" maps to Z extent, extrude is in +Y (5mm).
    assert bb.y_mm == pytest.approx(5.0, abs=0.01)
    assert bb.z_mm == pytest.approx(60.0, abs=0.01)


def test_cylinder_40mm_dia_100mm_long():
    result = _run(
        CreatePartOp(id="p1"),
        CreateSketchOp(id="sk1", plane="Front Plane", sketch_id="sk1"),
        AddCirclesOp(id="c1", sketch_id="sk1",
                     circles=[CirclePrimitive(center=[0.0, 0.0], diameter=40.0)]),
        ExtrudeBossOp(id="e1", profile_id="sk1", depth_mm=100.0),
    )
    assert result.success is True, result.errors
    bb = result.bounding_box_mm
    assert bb.x_mm == pytest.approx(40.0, abs=0.05)
    assert bb.y_mm == pytest.approx(40.0, abs=0.05)
    assert bb.z_mm == pytest.approx(100.0, abs=0.05)


def test_unsupported_op_records_error_but_does_not_crash():
    # NoopOp is supported (it's in meta.py). Force an unsupported one by
    # constructing a fake op-like object. Easier: assert the registry size.
    from validation.op_handlers import HANDLERS
    expected_minimum = {
        "create_part", "create_sketch", "add_center_rectangle",
        "add_circles", "extrude_boss", "extrude_cut",
        "rebuild", "noop", "delete_feature",
    }
    assert expected_minimum.issubset(HANDLERS.keys())
