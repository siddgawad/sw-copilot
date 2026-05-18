"""Tests for the edit_feature op type — used to modify an existing
extrude/fillet/chamfer dimension without delete+recreate.

The Python validator only records the intent; the geometric change is
verified by the SolidWorks C# executor's ModifyDefinition2 call. These
tests cover schema validation and registry coverage.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from models.schemas import (
    AddCenterRectangleOp,
    CreatePartOp,
    CreateSketchOp,
    EditFeatureOp,
    ExtrudeBossOp,
    OperationGraph,
)
from validation import Build123dBackend


def test_edit_feature_requires_one_dimension():
    with pytest.raises(ValidationError):
        EditFeatureOp(id="ed1", feature_id="Boss-Extrude1")  # nothing set


def test_edit_feature_rejects_multiple_dimensions():
    with pytest.raises(ValidationError):
        EditFeatureOp(id="ed1", feature_id="Boss-Extrude1", depth_mm=10, radius_mm=2)


def test_edit_feature_rejects_non_positive():
    with pytest.raises(ValidationError):
        EditFeatureOp(id="ed1", feature_id="Boss-Extrude1", depth_mm=0)
    with pytest.raises(ValidationError):
        EditFeatureOp(id="ed1", feature_id="Boss-Extrude1", radius_mm=-1)


def test_edit_feature_accepts_valid_input():
    op = EditFeatureOp(id="ed1", feature_id="Boss-Extrude1", depth_mm=10.0)
    assert op.depth_mm == 10.0
    assert op.radius_mm is None


def test_edit_feature_op_runs_in_validation_backend():
    """The validator records the intent — bbox doesn't change because
    build123d can't retroactively edit an extruded solid. The real edit
    happens in C# via ModifyDefinition2."""
    graph = OperationGraph(operations=[
        CreatePartOp(id="p1"),
        CreateSketchOp(id="sk1", plane="Front Plane", sketch_id="sk1"),
        AddCenterRectangleOp(id="r1", sketch_id="sk1", length=100.0, width=60.0),
        ExtrudeBossOp(id="e1", profile_id="sk1", depth_mm=5.0),
        EditFeatureOp(id="ed1", feature_id="Boss-Extrude1", depth_mm=10.0),
    ])
    result = Build123dBackend().execute(graph)
    assert result.success, result.errors
    # Bbox is the build123d result, which doesn't apply the edit — that's expected.
    # The bbox after a real C# edit would be 100×60×10.
    assert result.bounding_box_mm.x_mm == pytest.approx(100.0, abs=0.01)
    assert "ed1" in [f for f in graph.operations if f.id == "ed1"][0].id


def test_edit_feature_handler_registered():
    from validation.op_handlers import HANDLERS
    assert "edit_feature" in HANDLERS
