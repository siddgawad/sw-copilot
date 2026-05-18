"""Result types for the build123d validation backend.

`Build123dResult` mirrors the shape of `models.schemas.PartReport` so the
existing SolidWorks validation_agent works against it with zero changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.schemas import BoundingBox, PartReport


@dataclass(frozen=True)
class SketchInfo:
    """Mirror of models.schemas.PartSketchInfo. We only fill name + entity_count.

    `dimension_count` is always 0 for build123d output — it doesn't track
    smart dimensions, only geometric definition.
    """
    name: str
    entity_count: int
    dimension_count: int = 0


@dataclass(frozen=True)
class Build123dResult:
    """Geometric report from running an OperationGraph in build123d.

    Attributes
    ----------
    success
        True if every op handler ran without error.
    bounding_box_mm
        Bounding box of the final part. None if no part was created.
    body_count
        Number of solid bodies in the result.
    feature_count
        Number of named features registered in the execution context.
    sketches
        One SketchInfo per create_sketch op.
    errors
        Human-readable error strings prefixed with "[op_id] type: message".
        Empty list when success is True.
    """
    success: bool
    bounding_box_mm: "BoundingBox | None"
    body_count: int
    feature_count: int
    sketches: list[SketchInfo] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def matches_part_report(self, report: "PartReport", tolerance_mm: float = 0.5) -> bool:
        """Compare to a SolidWorks PartReport. Returns True if topology and
        bounding box agree within `tolerance_mm`.

        Used by the parity test harness — same OperationGraph → same geometry
        in build123d and SolidWorks.
        """
        if self.body_count != report.body_count:
            return False
        if self.bounding_box_mm is None or report.bounding_box is None:
            return self.bounding_box_mm is None and report.bounding_box is None
        a, b = self.bounding_box_mm, report.bounding_box
        return (
            abs(a.x_mm - b.x_mm) <= tolerance_mm
            and abs(a.y_mm - b.y_mm) <= tolerance_mm
            and abs(a.z_mm - b.z_mm) <= tolerance_mm
        )
