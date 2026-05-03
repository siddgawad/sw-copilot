"""
Post-execution validation: compare what the LLM asked SolidWorks to build
(`OperationGraph`) against what the C# executor reports actually exists in the
document (`PartReport` produced by `OperationExecutor.ExtractPartReport`).

This is pipeline step 7. Pure data comparison — no SolidWorks, no LLM.

Today's coverage:
  • Bounding-box check from the first sketch+extrude_boss combo (the base body).
  • Body-count sanity (should be exactly 1 for typical part graphs).
  • Feature-count plausibility (executable ops minus sketches ≤ feature_count).
  • Suppressed-feature detection (any suppressed user feature is flagged).

The bounding-box derivation only handles axis-aligned base extrudes from
`Top Plane | Front Plane | Right Plane`. More complex graphs fall back to
"unknown expected bbox" rather than emitting false positives.
"""

from __future__ import annotations

from models.schemas import (
    BoundingBox,
    CircleEntity,
    Discrepancy,
    ExtrudeBossOp,
    OperationGraph,
    PartReport,
    RectangleEntity,
    SketchOp,
    ValidationReport,
)


_PLANE_TO_EXTRUDE_AXIS: dict[str, str] = {
    "Top Plane":   "z",
    "Front Plane": "y",
    "Right Plane": "x",
}


def _expected_base_bbox(graph: OperationGraph) -> BoundingBox | None:
    """
    Derive the expected bounding box of the base body, if and only if the graph
    is a simple sketch + extrude_boss on a standard plane. Returns None for
    anything more elaborate.
    """
    sketches: dict[str, SketchOp] = {
        op.id: op for op in graph.operations if isinstance(op, SketchOp)
    }
    base_extrudes = [
        op for op in graph.operations if isinstance(op, ExtrudeBossOp)
    ]
    if len(base_extrudes) != 1:
        return None
    base_extrude = base_extrudes[0]

    sketch = sketches.get(base_extrude.profile_id)
    if sketch is None or sketch.plane not in _PLANE_TO_EXTRUDE_AXIS:
        return None
    if not sketch.entities:
        return None

    # Profile bounding rectangle from the first entity. Keeping this simple and
    # honest: rectangles and circles only.
    entity = sketch.entities[0]
    if isinstance(entity, RectangleEntity):
        u = abs(entity.x2_mm - entity.x1_mm)
        v = abs(entity.y2_mm - entity.y1_mm)
    elif isinstance(entity, CircleEntity):
        u = v = 2.0 * entity.radius_mm
    else:
        return None

    depth = base_extrude.depth_mm
    axis  = _PLANE_TO_EXTRUDE_AXIS[sketch.plane]
    if axis == "z":
        return BoundingBox(x_mm=u, y_mm=v, z_mm=depth)
    if axis == "y":
        return BoundingBox(x_mm=u, y_mm=depth, z_mm=v)
    return BoundingBox(x_mm=depth, y_mm=u, z_mm=v)  # axis == "x"


def _expected_feature_count_lower_bound(graph: OperationGraph) -> int:
    """
    Conservative lower bound on expected feature count. SW typically consumes a
    sketch into its parent feature, so we don't count sketches separately.
    Noops aren't executed. delete_feature shouldn't be counted.
    """
    countable = {
        "extrude_boss", "extrude_cut", "fillet", "chamfer",
        "hole_wizard", "circular_pattern", "linear_pattern",
        "mirror", "revolve",
    }
    return sum(1 for op in graph.operations if op.type in countable)


def _bbox_matches(a: BoundingBox, b: BoundingBox, tol: float) -> bool:
    return (
        abs(a.x_mm - b.x_mm) <= tol
        and abs(a.y_mm - b.y_mm) <= tol
        and abs(a.z_mm - b.z_mm) <= tol
    )


def validate(
    graph: OperationGraph,
    report: PartReport,
    tolerance_mm: float = 1.0,
) -> ValidationReport:
    discrepancies: list[Discrepancy] = []
    expected_summary: dict = {}
    actual_summary:   dict = {
        "body_count":    report.body_count,
        "feature_count": report.feature_count,
    }
    if report.bounding_box is not None:
        actual_summary["bounding_box"] = report.bounding_box.model_dump()

    # 1. Bounding-box check (only when we can derive expectation safely).
    expected_bbox = _expected_base_bbox(graph)
    if expected_bbox is not None:
        expected_summary["bounding_box"] = expected_bbox.model_dump()
        if report.bounding_box is None:
            discrepancies.append(Discrepancy(
                category="bounding_box",
                severity="warning",
                expected=expected_bbox.model_dump_json(),
                actual="null",
                message="Part report has no bounding box — cannot verify base body dimensions.",
            ))
        elif not _bbox_matches(expected_bbox, report.bounding_box, tolerance_mm):
            discrepancies.append(Discrepancy(
                category="bounding_box",
                severity="error",
                expected=expected_bbox.model_dump_json(),
                actual=report.bounding_box.model_dump_json(),
                message=(
                    f"Bounding box differs from request by more than "
                    f"{tolerance_mm} mm tolerance."
                ),
            ))

    # 2. Body count sanity. Most graphs should produce exactly one solid body.
    expected_summary["body_count"] = 1
    if report.body_count == 0:
        discrepancies.append(Discrepancy(
            category="body_count",
            severity="error",
            expected="1",
            actual="0",
            message="No solid body present — extrude likely failed.",
        ))
    elif report.body_count > 1:
        discrepancies.append(Discrepancy(
            category="body_count",
            severity="warning",
            expected="1",
            actual=str(report.body_count),
            message="Multiple bodies present — operations may not have merged.",
        ))

    # 3. Feature-count plausibility (lower bound).
    expected_min_features = _expected_feature_count_lower_bound(graph)
    expected_summary["feature_count_min"] = expected_min_features
    if report.feature_count < expected_min_features:
        discrepancies.append(Discrepancy(
            category="feature_count",
            severity="error",
            expected=f">= {expected_min_features}",
            actual=str(report.feature_count),
            message=(
                f"Fewer features than executable operations — at least "
                f"{expected_min_features - report.feature_count} op(s) "
                "did not produce a feature."
            ),
        ))

    # 4. Suppressed features. Any user-suppressed feature in a freshly executed
    # graph is suspicious — SW only suppresses on rebuild errors or hide ops.
    for feature in report.features:
        if feature.suppressed:
            discrepancies.append(Discrepancy(
                category="suppressed_feature",
                severity="warning",
                expected="not suppressed",
                actual=feature.name,
                message=f"Feature '{feature.name}' is suppressed — likely a rebuild error.",
            ))

    has_errors   = any(d.severity == "error"   for d in discrepancies)
    has_warnings = any(d.severity == "warning" for d in discrepancies)

    return ValidationReport(
        passed=not has_errors,
        has_warnings=has_warnings,
        discrepancies=discrepancies,
        expected_summary=expected_summary,
        actual_summary=actual_summary,
    )
