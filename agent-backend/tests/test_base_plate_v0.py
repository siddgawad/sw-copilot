from __future__ import annotations

import json
import asyncio

import pytest

from agents.base_plate_v0 import (
    build_coordinate_plan,
    parse_design_spec,
    try_compile_base_plate_v0,
    update_run_artifacts_after_validation,
    write_initial_run_artifacts,
)
from agents.validation_agent import validate
from main import generate
from models.schemas import (
    BoundingBox,
    DocumentContext,
    ExecutorOperationResult,
    ExecutorRunResult,
    GenerateRequest,
    PartFeatureInfo,
    PartReport,
    PartSketchInfo,
)


@pytest.mark.parametrize("prompt", [
    "make a 120x80x10 base plate",
    "make a 120x80x10mm base plate",
    "make a 120 by 80 by 10 mm base plate",
])
def test_base_plate_dimensions_parse(prompt):
    spec = parse_design_spec(prompt)
    assert spec.part_family == "base_plate"
    assert spec.parameters.length == 120
    assert spec.parameters.width == 80
    assert spec.parameters.thickness == 10
    assert spec.parameters.hole_count == 0
    assert spec.coordinate_system.plane == "Front"
    assert spec.missing_required_parameters == []


def test_base_plate_hole_prompt_generates_coordinate_plan():
    spec = parse_design_spec(
        "make a 120x80x10mm base plate with four 6mm through holes 10mm from corners"
    )
    plan = build_coordinate_plan(spec)

    assert spec.parameters.hole_count == 4
    assert spec.parameters.hole_diameter == 6
    assert plan.base_rectangle.corners == [
        [-60.0, -40.0],
        [60.0, -40.0],
        [60.0, 40.0],
        [-60.0, 40.0],
    ]
    assert [hole.center for hole in plan.holes] == [
        [-50.0, -30.0],
        [50.0, -30.0],
        [50.0, 30.0],
        [-50.0, 30.0],
    ]


def test_base_plate_default_hole_offset_is_deterministic():
    result = try_compile_base_plate_v0(
        "make a 120x80x10mm base plate with four 6mm holes"
    )

    assert result is not None
    assert result.design_spec.parameters.hole_offset_x == 10
    assert any("defaulted omitted corner-hole offsets" in a for a in result.design_spec.assumptions)
    assert [hole.center for hole in result.coordinate_plan.holes] == [
        [-50.0, -30.0],
        [50.0, -30.0],
        [50.0, 30.0],
        [-50.0, 30.0],
    ]


def test_invalid_hole_offset_rejected_before_operation_graph():
    with pytest.raises(ValueError, match="hole radius must be smaller"):
        try_compile_base_plate_v0(
            "make a 120x80x10mm base plate with four 30mm holes 10mm from corners"
        )


def test_operation_graph_uses_coordinate_first_v02_ops():
    result = try_compile_base_plate_v0(
        "make a 120x80x10mm base plate with four 6mm holes 10mm from corners"
    )
    assert result is not None

    graph = result.operation_graph
    assert graph.part_family == "base_plate_v0"
    assert graph.trace_id is None
    assert [op.type for op in graph.operations] == [
        "create_part",
        "create_sketch",
        "add_center_rectangle",
        "extrude_boss",
        "create_sketch",
        "add_circles",
        "extrude_cut",
        "rebuild",
    ]
    assert graph.operations[1].plane == "Front Plane"
    assert result.sketch_graph.sketches[0].plane == "Front"
    add_circles = graph.operations[5]
    assert add_circles.type == "add_circles"
    assert len(add_circles.circles) == 4


def test_run_artifacts_written_and_updated(tmp_path, monkeypatch):
    monkeypatch.setenv("SW_COPILOT_RUNS_DIR", str(tmp_path))
    result = try_compile_base_plate_v0(
        "make a 120x80x10mm base plate with four 6mm holes 10mm from corners"
    )
    assert result is not None

    trace_id, run_dir = write_initial_run_artifacts("make a base plate", result)

    assert trace_id == result.operation_graph.trace_id
    for name in [
        "prompt.txt",
        "design_spec.json",
        "coordinate_plan.json",
        "sketch_graph.json",
        "operation_graph.json",
        "executor_result.json",
        "part_report.json",
        "validation_report.json",
        "timing.json",
        "final_status.json",
    ]:
        assert (run_dir / name).exists()

    report = _passing_part_report()
    validation = validate(result.operation_graph, report, executor_result=_passing_executor_result())
    update_run_artifacts_after_validation(
        result.operation_graph,
        report,
        validation,
        _passing_executor_result(),
    )

    final = json.loads((run_dir / "final_status.json").read_text(encoding="utf-8"))
    assert final["status"] == "passed"
    assert final["passed"] is True


def test_validator_passes_mocked_base_plate_report():
    result = try_compile_base_plate_v0(
        "make a 120x80x10mm base plate with four 6mm holes 10mm from corners"
    )
    assert result is not None

    validation = validate(
        result.operation_graph,
        _passing_part_report(),
        tolerance_mm=0.1,
        executor_result=_passing_executor_result(),
    )

    assert validation.passed is True
    assert validation.discrepancies == []


def test_validator_fails_when_hole_sketch_count_differs():
    result = try_compile_base_plate_v0(
        "make a 120x80x10mm base plate with four 6mm holes 10mm from corners"
    )
    assert result is not None
    report = _passing_part_report(hole_entities=3)

    validation = validate(result.operation_graph, report, executor_result=_passing_executor_result())

    assert validation.passed is False
    assert any(d.category == "sketch_entity_count" for d in validation.discrepancies)


def test_generate_base_plate_does_not_require_initialised_llm_agents(tmp_path, monkeypatch):
    """Plate prompts route through the deterministic pattern router — no LLM.

    Legacy base_plate_v0 intercept was removed (it returned wrong dims and
    blocked the better patterns/plate.py router). design_spec /
    coordinate_plan / sketch_graph are no longer surfaced on this path; the
    invariant we still care about is "no LLM call required".
    """
    monkeypatch.setenv("SW_COPILOT_RUNS_DIR", str(tmp_path))
    response = asyncio.run(generate(GenerateRequest(
        prompt="make a 120x80x10mm base plate with four 6mm holes 10mm from corners",
        context=DocumentContext(document_type="Part"),
    )))

    assert response.operation_graph is not None
    assert "no LLM call required" in response.status_message


def _passing_part_report(hole_entities: int = 4) -> PartReport:
    return PartReport(
        document_type="part",
        rebuild_status="success",
        body_count=1,
        bounding_box=BoundingBox(x_mm=120, y_mm=80, z_mm=10),
        feature_count=2,
        features=[
            PartFeatureInfo(name="BasePlate_Extrude", type="Boss"),
            PartFeatureInfo(name="Mounting_Holes_Cut", type="Cut"),
        ],
        sketches=[
            PartSketchInfo(name="base_profile", entity_count=4),
            PartSketchInfo(name="hole_profile", entity_count=hole_entities),
        ],
    )


def _passing_executor_result() -> ExecutorRunResult:
    return ExecutorRunResult(
        status="success",
        operations=[
            ExecutorOperationResult(operation_id="op_001", operation_type="create_part", status="success"),
            ExecutorOperationResult(operation_id="op_004", operation_type="extrude_boss", status="success"),
            ExecutorOperationResult(operation_id="op_007", operation_type="extrude_cut", status="success"),
        ],
    )
