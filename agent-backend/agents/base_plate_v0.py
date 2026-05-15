from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from models.schemas import (
    AddCenterRectangleOp,
    AddCirclesOp,
    BasePlateParameters,
    BaseRectanglePlan,
    CirclePrimitive,
    CoordinateHole,
    CoordinatePlan,
    CoordinateSystemSpec,
    CreatePartOp,
    CreateSketchOp,
    DesignSpec,
    ExecutorRunResult,
    ExtrudeBossOp,
    ExtrudeCutOp,
    NoopOp,
    OperationGraph,
    PartReport,
    RebuildOp,
    SketchGraph,
    SketchGraphSketch,
    ValidationReport,
)


_DIM_RE = re.compile(
    r"(?P<a>\d+(?:\.\d+)?)\s*(?:mm)?\s*(?:x|by)\s*"
    r"(?P<b>\d+(?:\.\d+)?)\s*(?:mm)?\s*(?:x|by)\s*"
    r"(?P<c>\d+(?:\.\d+)?)\s*(?:mm)?",
    re.IGNORECASE,
)
_HOLE_DIAMETER_RE = re.compile(r"\b(?P<d>\d+(?:\.\d+)?)\s*mm\s+(?:through\s+)?holes?\b", re.IGNORECASE)
_HOLE_OFFSET_RE = re.compile(r"\b(?P<o>\d+(?:\.\d+)?)\s*mm\s+from\s+corners?\b", re.IGNORECASE)
_FOUR_HOLES_RE = re.compile(r"\b(four|4)\s+(?:\d+(?:\.\d+)?\s*mm\s+)?(?:through\s+)?holes?\b", re.IGNORECASE)


@dataclass(frozen=True)
class BasePlateCompileResult:
    design_spec: DesignSpec
    coordinate_plan: CoordinatePlan
    sketch_graph: SketchGraph
    operation_graph: OperationGraph
    timing_ms: dict[str, int]


def try_compile_base_plate_v0(prompt: str) -> BasePlateCompileResult | None:
    """Return a deterministic v0.2 base-plate plan, or None when the prompt is
    outside this intentionally tiny product slice."""
    normalized = _normalize_prompt(prompt)
    if "base plate" not in normalized and "plate" not in normalized:
        return None

    t0 = time.perf_counter()
    spec = parse_design_spec(prompt)
    t1 = time.perf_counter()
    if spec.missing_required_parameters:
        plan = CoordinatePlan(
            base_rectangle=BaseRectanglePlan(center=[0.0, 0.0], length=0.0, width=0.0, corners=[]),
            holes=[],
        )
        sketch_graph = SketchGraph(sketches=[])
        operation_graph = OperationGraph(
            part_family="base_plate_v0",
            part_name="base_plate",
            missing_inputs=spec.missing_required_parameters,
            assumptions=[],
            operations=[
                NoopOp(
                    id="noop1",
                    message="base_plate_v0 needs: " + ", ".join(spec.missing_required_parameters),
                )
            ],
        )
        now = time.perf_counter()
        timing = {
            "parse": _elapsed_ms(t0, t1),
            "coordinate_plan": 0,
            "sketch_graph": 0,
            "operation_graph": _elapsed_ms(t1, now),
            "solidworks_execution": 0,
            "part_report_extraction": 0,
            "validation": 0,
            "total": _elapsed_ms(t0, now),
        }
        return BasePlateCompileResult(spec, plan, sketch_graph, operation_graph, timing)

    plan = build_coordinate_plan(spec)
    t2 = time.perf_counter()
    sketch_graph = build_sketch_graph(spec, plan)
    t3 = time.perf_counter()
    operation_graph = build_operation_graph(spec, plan)
    t4 = time.perf_counter()

    timing = {
        "parse": _elapsed_ms(t0, t1),
        "coordinate_plan": _elapsed_ms(t1, t2),
        "sketch_graph": _elapsed_ms(t2, t3),
        "operation_graph": _elapsed_ms(t3, t4),
        "solidworks_execution": 0,
        "part_report_extraction": 0,
        "validation": 0,
        "total": _elapsed_ms(t0, t4),
    }
    return BasePlateCompileResult(spec, plan, sketch_graph, operation_graph, timing)


def parse_design_spec(prompt: str) -> DesignSpec:
    normalized = _normalize_prompt(prompt)
    dim_match = _DIM_RE.search(normalized)
    if not dim_match:
        return _unsupported_spec("base plate dimensions as length x width x thickness")

    length = float(dim_match.group("a"))
    width = float(dim_match.group("b"))
    thickness = float(dim_match.group("c"))
    assumptions = [
        f"{_fmt(length)}mm length is along X-axis",
        f"{_fmt(width)}mm width is along Y-axis",
        f"{_fmt(thickness)}mm thickness extrudes along +Z",
        "SolidWorks Front Plane is used as the XY sketch plane for this v0.2 path",
        "plate is centered at global origin",
        "base sketch is intended to be fully defined",
    ]

    hole_count = 0
    hole_diameter: float | None = None
    offset_x: float | None = None
    offset_y: float | None = None

    if "hole" in normalized:
        if not _FOUR_HOLES_RE.search(normalized):
            return _unsupported_spec("base_plate_v0 supports exactly four holes")
        hole_count = 4
        diameter_match = _HOLE_DIAMETER_RE.search(normalized)
        if not diameter_match:
            return _unsupported_spec("hole diameter in millimetres")
        hole_diameter = float(diameter_match.group("d"))
        offset_match = _HOLE_OFFSET_RE.search(normalized)
        offset = float(offset_match.group("o")) if offset_match else 10.0
        offset_x = offset_y = offset
        assumptions.extend([
            f"{_fmt(hole_diameter)}mm holes means diameter, not radius",
            "holes are through-all cuts",
            f"hole centers are {_fmt(offset)}mm from nearest two outer edges",
        ])
        if not offset_match:
            assumptions.append("base_plate_v0 defaulted omitted corner-hole offsets to 10mm")

    spec = DesignSpec(
        parameters=BasePlateParameters(
            length=length,
            width=width,
            thickness=thickness,
            hole_count=hole_count,
            hole_diameter=hole_diameter,
            hole_offset_x=offset_x,
            hole_offset_y=offset_y,
        ),
        coordinate_system=CoordinateSystemSpec(),
        assumptions=assumptions,
    )
    _validate_design_spec(spec)
    return spec


def build_coordinate_plan(spec: DesignSpec) -> CoordinatePlan:
    p = spec.parameters
    left = -p.length / 2.0
    right = p.length / 2.0
    bottom = -p.width / 2.0
    top = p.width / 2.0

    holes: list[CoordinateHole] = []
    if p.hole_count:
        ox = p.hole_offset_x or 0.0
        oy = p.hole_offset_y or 0.0
        diameter = p.hole_diameter or 0.0
        centers = [
            [left + ox, bottom + oy],
            [right - ox, bottom + oy],
            [right - ox, top - oy],
            [left + ox, top - oy],
        ]
        holes = [
            CoordinateHole(id=f"hole_{idx}", center=center, diameter=diameter)
            for idx, center in enumerate(centers, start=1)
        ]

    return CoordinatePlan(
        base_rectangle=BaseRectanglePlan(
            center=[0.0, 0.0],
            length=p.length,
            width=p.width,
            corners=[
                [left, bottom],
                [right, bottom],
                [right, top],
                [left, top],
            ],
        ),
        holes=holes,
    )


def build_sketch_graph(spec: DesignSpec, plan: CoordinatePlan) -> SketchGraph:
    p = spec.parameters
    sketches = [
        SketchGraphSketch(
            id="base_profile",
            plane="Front",
            entities=[{
                "id": "base_rect",
                "type": "center_rectangle",
                "center": [0.0, 0.0],
                "length": p.length,
                "width": p.width,
            }],
            constraints=[
                {"type": "coincident", "target": "base_rect.center", "reference": "origin"},
                {"type": "horizontal_vertical", "target": "base_rect"},
            ],
            dimensions=[
                {"name": "Plate_Length", "value": p.length, "units": "mm", "driving": True},
                {"name": "Plate_Width", "value": p.width, "units": "mm", "driving": True},
            ],
        )
    ]

    if plan.holes:
        sketches.append(
            SketchGraphSketch(
                id="hole_profile",
                plane="top_face_of:BasePlate_Extrude",
                entities=[
                    {"id": h.id, "type": "circle", "center": h.center, "diameter": h.diameter}
                    for h in plan.holes
                ],
                dimensions=[
                    {"name": "Hole_Diameter", "value": p.hole_diameter, "units": "mm", "driving": True},
                    {"name": "Hole_Offset_X", "value": p.hole_offset_x, "units": "mm", "driving": True},
                    {"name": "Hole_Offset_Y", "value": p.hole_offset_y, "units": "mm", "driving": True},
                ],
            )
        )

    return SketchGraph(sketches=sketches)


def build_operation_graph(spec: DesignSpec, plan: CoordinatePlan) -> OperationGraph:
    p = spec.parameters
    operations = [
        CreatePartOp(id="op_001"),
        # In this SolidWorks 2021 executor, Front Plane sketches map sketch X/Y
        # to model X/Y and extrude depth to model Z. Top Plane maps sketch Y to
        # model Z, which makes plates stand on edge and places follow-up hole
        # sketches off the intended face.
        CreateSketchOp(id="op_002", plane="Front Plane", sketch_id="base_profile"),
        AddCenterRectangleOp(
            id="op_003",
            sketch_id="base_profile",
            center=[0.0, 0.0],
            length=p.length,
            width=p.width,
        ),
        ExtrudeBossOp(
            id="op_004",
            profile_id="base_profile",
            sketch_id="base_profile",
            depth_mm=p.thickness,
            depth=p.thickness,
            name="BasePlate_Extrude",
            feature_name="BasePlate_Extrude",
            direction="+normal",
        ),
    ]

    if plan.holes:
        operations.extend([
            CreateSketchOp(
                id="op_005",
                plane="top_face_of:BasePlate_Extrude",
                sketch_id="hole_profile",
            ),
            AddCirclesOp(
                id="op_006",
                sketch_id="hole_profile",
                circles=[
                    CirclePrimitive(center=h.center, diameter=h.diameter)
                    for h in plan.holes
                ],
            ),
            ExtrudeCutOp(
                id="op_007",
                profile_id="hole_profile",
                sketch_id="hole_profile",
                feature_name="Mounting_Holes_Cut",
                name="Mounting_Holes_Cut",
                cut_type="through_all",
                through_all=True,
                depth_mm=0.0,
            ),
        ])

    operations.append(RebuildOp(id=f"op_{len(operations) + 1:03d}"))

    return OperationGraph(
        part_family="base_plate_v0",
        part_name="base_plate",
        reasoning="Deterministic base_plate_v0 parser computed all coordinates from explicit dimensions.",
        assumptions=spec.assumptions,
        missing_inputs=spec.missing_required_parameters,
        operations=operations,
    )


def write_initial_run_artifacts(prompt: str, result: BasePlateCompileResult) -> tuple[str, Path]:
    trace_id, run_dir = _new_run_dir(prompt)
    result.operation_graph.trace_id = trace_id
    run_dir.mkdir(parents=True, exist_ok=False)

    _write_text(run_dir / "prompt.txt", prompt)
    _write_json(run_dir / "design_spec.json", result.design_spec)
    _write_json(run_dir / "coordinate_plan.json", result.coordinate_plan)
    _write_json(run_dir / "sketch_graph.json", result.sketch_graph)
    _write_json(run_dir / "operation_graph.json", result.operation_graph)
    _write_json(run_dir / "executor_result.json", ExecutorRunResult())
    _write_json(run_dir / "part_report.json", {})
    _write_json(run_dir / "validation_report.json", {})
    _write_json(run_dir / "timing.json", {"timing_ms": result.timing_ms})
    _write_json(run_dir / "final_status.json", {
        "trace_id": trace_id,
        "status": "planned",
        "passed": None,
    })
    return trace_id, run_dir


def update_run_artifacts_after_validation(
    graph: OperationGraph,
    part_report: PartReport,
    validation_report: ValidationReport,
    executor_result: ExecutorRunResult | None = None,
) -> None:
    if not graph.trace_id:
        return
    run_dir = runs_root() / graph.trace_id
    if not run_dir.exists():
        return

    if executor_result is not None:
        _write_json(run_dir / "executor_result.json", executor_result)
    _write_json(run_dir / "part_report.json", part_report)
    _write_json(run_dir / "validation_report.json", validation_report)
    _write_json(run_dir / "final_status.json", {
        "trace_id": graph.trace_id,
        "status": "passed" if validation_report.passed else "failed",
        "passed": validation_report.passed,
        "warnings": validation_report.has_warnings,
    })


def runs_root() -> Path:
    override = os.environ.get("SW_COPILOT_RUNS_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "runs"


def _unsupported_spec(missing: str) -> DesignSpec:
    return DesignSpec(
        parameters=BasePlateParameters(length=0, width=0, thickness=0),
        assumptions=[],
        missing_required_parameters=[missing],
    )


def _validate_design_spec(spec: DesignSpec) -> None:
    p = spec.parameters
    errors: list[str] = []
    if p.length <= 0:
        errors.append("length must be positive")
    if p.width <= 0:
        errors.append("width must be positive")
    if p.thickness <= 0:
        errors.append("thickness must be positive")

    if p.hole_count:
        radius = (p.hole_diameter or 0.0) / 2.0
        ox = p.hole_offset_x or 0.0
        oy = p.hole_offset_y or 0.0
        if p.hole_count != 4:
            errors.append("base_plate_v0 supports exactly four holes")
        if radius <= 0:
            errors.append("hole diameter must be positive")
        if ox <= 0 or oy <= 0:
            errors.append("hole offsets must be positive")
        if radius >= ox:
            errors.append("hole radius must be smaller than hole_offset_x")
        if radius >= oy:
            errors.append("hole radius must be smaller than hole_offset_y")
        if ox >= p.length / 2.0 or oy >= p.width / 2.0:
            errors.append("hole centers must lie inside plate boundary")

    if errors:
        raise ValueError("; ".join(errors))


def _normalize_prompt(prompt: str) -> str:
    return re.sub(r"\s+", " ", prompt.lower().replace("×", "x")).strip()


def _elapsed_ms(start: float, end: float) -> int:
    return int(round((end - start) * 1000))


def _new_run_dir(prompt: str) -> tuple[str, Path]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    slug = re.sub(r"[^a-z0-9]+", "-", prompt.lower())[:48].strip("-") or "run"
    trace_id = f"{stamp}_{slug}"
    return trace_id, runs_root() / trace_id


def _write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def _write_json(path: Path, value: Any) -> None:
    if hasattr(value, "model_dump"):
        payload = value.model_dump(mode="json")
    else:
        payload = value
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _fmt(value: float) -> str:
    return f"{value:g}"
