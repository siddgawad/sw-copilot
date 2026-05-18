"""Tests for CircularPatternHandler / LinearPatternHandler / MirrorHandler."""
from __future__ import annotations

import pytest

from models.schemas import (
    AddCirclesOp,
    CirclePrimitive,
    CircularPatternOp,
    CreatePartOp,
    CreateSketchOp,
    ExtrudeBossOp,
    ExtrudeCutOp,
    OperationGraph,
)
from validation import Build123dBackend


def test_flange_with_6_bolt_holes_on_60mm_pcd():
    """Canonical bolt-circle case: 80mm diameter × 6mm thick flange with
    6 × M5 holes on 60mm PCD. After cut + pattern, bbox stays 80×80×6."""
    graph = OperationGraph(operations=[
        CreatePartOp(id="p1"),
        CreateSketchOp(id="sk1", plane="Front Plane", sketch_id="sk1"),
        AddCirclesOp(id="c1", sketch_id="sk1",
                     circles=[CirclePrimitive(center=[0.0, 0.0], diameter=80.0)]),
        ExtrudeBossOp(id="e1", profile_id="sk1", depth_mm=6.0),
        # one source hole
        CreateSketchOp(id="sk2", plane="Front Plane", sketch_id="sk2"),
        AddCirclesOp(id="c2", sketch_id="sk2",
                     circles=[CirclePrimitive(center=[30.0, 0.0], diameter=5.5)]),
        ExtrudeCutOp(id="cut1", profile_id="sk2", through_all=True),
        # pattern around the axis
        CircularPatternOp(id="cp1", source_ids=["cut1"], count=6, pcd_mm=60.0),
    ])
    result = Build123dBackend().execute(graph)
    assert result.success, result.errors
    bb = result.bounding_box_mm
    assert bb.x_mm == pytest.approx(80.0, abs=0.1)
    assert bb.y_mm == pytest.approx(80.0, abs=0.1)
    assert bb.z_mm == pytest.approx(6.0, abs=0.05)
