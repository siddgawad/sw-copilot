"""Mutable per-graph execution state passed through op handlers.

Why a mutable context instead of a chain of return values:
    build123d uses Python with-blocks (BuildPart, BuildSketch) that hold
    geometric state implicitly. A single context that handlers append to
    matches that model and keeps handler signatures uniform.

Handlers must never read or write attributes not defined on the context.
If you need new state, add it here and update the design doc.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .result import Build123dResult, SketchInfo


@dataclass
class _SketchRecord:
    """Captured sketch geometry. We don't keep the build123d Sketch object
    after the BuildPart with-block closes — only the metadata."""
    name: str
    plane_name: str
    entity_count: int


@dataclass
class ExecutionContext:
    """All state shared across op handlers for one OperationGraph run.

    Attributes
    ----------
    parts
        Map op_id → build123d Part object. Populated by create_part /
        extrude_boss / hole_wizard. The "active" part is the last one
        added unless `active_part_id` is set.
    pending_sketch
        Stash for the most-recently-built Sketch *before* it is consumed
        by an extrude / cut op. Handlers should pop it via `take_sketch`.
    sketch_records
        One _SketchRecord per create_sketch op for the final result.
    features
        op_id → feature kind ("boss", "cut", "hole", "fillet", ...). Used
        by the result to compute feature_count and by handlers that
        reference earlier features by op_id (face_of, profile_id).
    active_part_id
        Explicit active part. None means "use most recent".
    errors
        Per-op error messages. Append via add_error.
    extras
        Free-form scratchpad for handlers that need to communicate
        out-of-band (e.g. circle_diameter passed from add_circles to
        extrude_cut). Prefer typed attributes when possible.
    """
    parts: dict[str, Any] = field(default_factory=dict)
    pending_sketch: Any = None
    pending_sketch_plane: Any = None
    sketch_records: list[_SketchRecord] = field(default_factory=list)
    features: dict[str, str] = field(default_factory=dict)
    active_part_id: str | None = None
    errors: list[str] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)

    def add_error(self, op_id: str, error_class: str, message: str) -> None:
        """Append a structured error string. Never raise from here."""
        self.errors.append(f"[{op_id}] {error_class}: {message}")

    def active_part(self) -> Any:
        """Return the currently active Part object.

        Raises
        ------
        RuntimeError
            If no part has been created yet.
        """
        if self.active_part_id and self.active_part_id in self.parts:
            return self.parts[self.active_part_id]
        if not self.parts:
            raise RuntimeError("No part exists in this context — create_part must run first.")
        # Default: most recently added part.
        return list(self.parts.values())[-1]

    def take_sketch(self) -> tuple[Any, Any]:
        """Pop the pending sketch and the plane it was built on.

        Returns
        -------
        (sketch, plane)
            sketch is a build123d Sketch; plane is a build123d Plane.

        Raises
        ------
        RuntimeError
            If no sketch is pending.
        """
        if self.pending_sketch is None:
            raise RuntimeError("No sketch is pending — create_sketch must run before extrude.")
        sk, pl = self.pending_sketch, self.pending_sketch_plane
        self.pending_sketch = None
        self.pending_sketch_plane = None
        return sk, pl

    def to_result(self) -> Build123dResult:
        """Snapshot the context into an immutable Build123dResult."""
        from models.schemas import BoundingBox

        bbox: BoundingBox | None = None
        body_count = 0

        # Find any real (non-None) part for bbox computation. A bare
        # create_part with no following extrude leaves a None entry —
        # treat as zero geometry, not an error.
        real_parts = [p for p in self.parts.values() if p is not None]
        if real_parts:
            part = self.active_part()
            if part is not None:
                try:
                    bb = part.bounding_box()
                    bbox = BoundingBox(
                        x_mm=round(bb.size.X, 3),
                        y_mm=round(bb.size.Y, 3),
                        z_mm=round(bb.size.Z, 3),
                    )
                    solids = part.solids() if hasattr(part, "solids") else []
                    body_count = max(1, len(solids))
                except Exception as exc:  # bbox/solid extraction failed
                    self.errors.append(f"[result] BBoxError: {exc}")

        return Build123dResult(
            success=len(self.errors) == 0,
            bounding_box_mm=bbox,
            body_count=body_count,
            feature_count=len(self.features),
            sketches=[
                SketchInfo(name=r.name, entity_count=r.entity_count)
                for r in self.sketch_records
            ],
            errors=list(self.errors),
        )
