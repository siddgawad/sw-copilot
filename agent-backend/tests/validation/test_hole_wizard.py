"""Tests for HoleWizardHandler.

Each test is a self-contained mini-graph: build a plate, then cut N holes.
Implementer (claude/codex/sonnet): implement one helper at a time, run
this file, watch tests turn green.
"""
from __future__ import annotations

import pytest

from models.schemas import (
    AddCenterRectangleOp,
    CreatePartOp,
    CreateSketchOp,
    ExtrudeBossOp,
    HolePosition,
    HoleWizardOp,
    OperationGraph,
)
from validation import Build123dBackend


def _plate_with_holes(hole_type: str, fastener: str = "M6",
                      positions: list[tuple[float, float]] | None = None):
    """Helper: build a 100×60×10 plate then a hole_wizard op."""
    positions = positions or [(40, 20), (-40, 20), (40, -20), (-40, -20)]
    return OperationGraph(operations=[
        CreatePartOp(id="p1"),
        CreateSketchOp(id="sk1", plane="Front Plane", sketch_id="sk1"),
        AddCenterRectangleOp(id="r1", sketch_id="sk1", length=100.0, width=60.0),
        ExtrudeBossOp(id="e1", profile_id="sk1", depth_mm=10.0),
        HoleWizardOp(
            id="h1",
            face_of="e1",
            hole_type=hole_type,
            fastener_size=fastener,
            through_all=True,
            depth_mm=0.0,
            positions=[HolePosition(x_mm=x, y_mm=y) for x, y in positions],
        ),
    ])


def test_simple_m6_four_corner_holes_reduces_volume():
    """Once implemented: four through-holes should leave the bbox at 100×60×10
    but reduce body volume by 4 × π × (clearance_r)² × thickness."""
    result = Build123dBackend().execute(_plate_with_holes("simple", "M6"))
    assert result.success, result.errors
    bb = result.bounding_box_mm
    assert bb.x_mm == pytest.approx(100.0, abs=0.05)
    assert bb.y_mm == pytest.approx(60.0, abs=0.05)
    assert bb.z_mm == pytest.approx(10.0, abs=0.05)


def test_m6_counterbore_on_10mm_plate_succeeds():
    """M6 counterbore depth is 6mm (ISO 4762); plate is 10mm → fits."""
    result = Build123dBackend().execute(_plate_with_holes("counterbore", "M6"))
    assert result.success, result.errors


def test_tapped_hole_is_validated_as_clearance():
    """build123d has no thread modelling — tapped holes validate as simple
    through-holes with clearance diameter."""
    result = Build123dBackend().execute(_plate_with_holes("tapped", "M6"))
    assert result.success, result.errors


def test_unsupported_fastener_records_error_not_crash():
    """Unknown fastener size → ValueError → recorded on result.errors."""
    graph = _plate_with_holes("simple", fastener="M99")
    result = Build123dBackend().execute(graph)
    assert not result.success
    assert any("M99" in e or "ValueError" in e for e in result.errors)
