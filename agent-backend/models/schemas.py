from __future__ import annotations

from typing import Annotated, Any, List, Literal, Optional, Union
from pydantic import BaseModel, Field, model_validator


# ── Request / context types ───────────────────────────────────────────────────

class BoundingBox(BaseModel):
    x_mm: float
    y_mm: float
    z_mm: float


class DocumentContext(BaseModel):
    document_type: str       = Field("None", description="Part | Assembly | Drawing | None")
    body_count:    int       = 0
    selected_ids:  list[str] = Field(default_factory=list)
    file_path:     str       = ""
    bounding_box_mm: Optional[BoundingBox] = None


class ConversationMessage(BaseModel):
    role:    str  # "user" | "assistant"
    content: str


class GenerateRequest(BaseModel):
    prompt:   str
    context:  DocumentContext            = Field(default_factory=DocumentContext)
    messages: List[ConversationMessage]  = Field(default_factory=list)  # prior turns, oldest first


# ── v0.2 deterministic design artifacts ─────────────────────────────────────

class BasePlateParameters(BaseModel):
    length: float
    width: float
    thickness: float
    hole_count: int = 0
    hole_diameter: Optional[float] = None
    hole_offset_x: Optional[float] = None
    hole_offset_y: Optional[float] = None
    hole_depth_type: Literal["through_all"] = "through_all"


class CoordinateSystemSpec(BaseModel):
    # SolidWorks Front Plane is the XY sketch plane; extruding its normal gives
    # model Z thickness for the base_plate_v0 coordinate contract.
    plane: Literal["Front", "Top"] = "Front"
    origin_strategy: Literal["centered_on_global_origin"] = "centered_on_global_origin"
    length_axis: Literal["X"] = "X"
    width_axis: Literal["Y"] = "Y"
    thickness_axis: Literal["+Z"] = "+Z"


class DesignSpec(BaseModel):
    part_family: Literal["base_plate"] = "base_plate"
    units: Literal["mm"] = "mm"
    parameters: BasePlateParameters
    coordinate_system: CoordinateSystemSpec = Field(default_factory=CoordinateSystemSpec)
    assumptions: List[str] = Field(default_factory=list)
    missing_required_parameters: List[str] = Field(default_factory=list)


class BaseRectanglePlan(BaseModel):
    center: List[float]
    length: float
    width: float
    corners: List[List[float]]


class CoordinateHole(BaseModel):
    id: str
    center: List[float]
    diameter: float


class CoordinatePlan(BaseModel):
    units: Literal["mm"] = "mm"
    base_rectangle: BaseRectanglePlan
    holes: List[CoordinateHole] = Field(default_factory=list)


class SketchGraphSketch(BaseModel):
    id: str
    plane: str
    units: Literal["mm"] = "mm"
    entities: List[dict[str, Any]] = Field(default_factory=list)
    constraints: List[dict[str, Any]] = Field(default_factory=list)
    dimensions: List[dict[str, Any]] = Field(default_factory=list)
    expected_status: str = "fully_defined"


class SketchGraph(BaseModel):
    sketches: List[SketchGraphSketch] = Field(default_factory=list)


class ExecutorOperationResult(BaseModel):
    operation_id: str
    operation_type: str
    status: Literal["success", "failed"]
    created_feature: Optional[str] = None
    error_type: Optional[str] = None
    message: Optional[str] = None


class ExecutorRunResult(BaseModel):
    status: Literal["success", "failed", "not_executed"] = "not_executed"
    operations: List[ExecutorOperationResult] = Field(default_factory=list)


# ── Legacy CadCommand (kept for test-suite backward-compatibility only) ───────

class DimensionsMeters(BaseModel):
    length:   Optional[float] = Field(default=None, ge=0)
    width:    Optional[float] = Field(default=None, ge=0)
    height:   Optional[float] = Field(default=None, ge=0)
    radius:   Optional[float] = Field(default=None, ge=0)
    diameter: Optional[float] = Field(default=None, ge=0)
    depth:    Optional[float] = Field(default=None, ge=0)


class CadCommand(BaseModel):
    action: Literal[
        "create_shape", "extrude_selected",
        "delete_all", "delete_named", "delete_last_n",
        "noop",
    ]
    shape_type: Literal["box", "cylinder", "none"] = "none"
    dimensions_meters: DimensionsMeters = Field(default_factory=DimensionsMeters)
    target_plane: Literal["Top Plane", "Front Plane", "Right Plane"] = "Top Plane"
    target_face: Optional[str] = None
    target_reference: Optional[dict] = None
    tolerance: float = Field(default=0.000001, ge=0)
    clear_existing: bool = False
    message: str = ""

    @model_validator(mode="after")
    def validate_executable_dimensions(self) -> "CadCommand":
        dims = self.dimensions_meters

        if self.action == "create_shape" and self.shape_type == "box":
            if dims.height is None and dims.depth is not None:
                dims.height = dims.depth
            missing = [
                name for name, value in (
                    ("length", dims.length),
                    ("width",  dims.width),
                    ("height", dims.height),
                )
                if value is None or value <= 0
            ]
            if missing:
                raise ValueError("box command missing positive dimensions: " + ", ".join(missing))

        if self.action == "create_shape" and self.shape_type == "cylinder":
            if dims.height is None and dims.depth is not None:
                dims.height = dims.depth
            has_radius   = dims.radius   is not None and dims.radius   > 0
            has_diameter = dims.diameter is not None and dims.diameter > 0
            if not has_radius and not has_diameter:
                raise ValueError("cylinder command missing positive radius or diameter")
            if dims.height is None or dims.height <= 0:
                raise ValueError("cylinder command missing positive height")

        if self.action == "extrude_selected":
            if dims.depth is None and dims.height is not None:
                dims.depth = dims.height
            if dims.depth is None or dims.depth <= 0:
                raise ValueError("extrude_selected command missing positive depth")

        if self.action in ("delete_all", "noop", "delete_named", "delete_last_n") and self.shape_type != "none":
            raise ValueError(f"{self.action} command must use shape_type='none'")

        if self.action == "delete_named":
            ref   = self.target_reference or {}
            names = ref.get("feature_names", [])
            if not isinstance(names, list) or not names:
                raise ValueError(
                    "delete_named requires target_reference.feature_names as a non-empty list of strings"
                )

        if self.action == "delete_last_n":
            ref   = self.target_reference or {}
            count = ref.get("last_n_count", 0)
            if not isinstance(count, int) or count <= 0:
                raise ValueError(
                    "delete_last_n requires target_reference.last_n_count as a positive integer"
                )

        return self


# ── Operation Graph IR ────────────────────────────────────────────────────────
# Primary execution path.  All dimensions in millimetres throughout.

class RectangleEntity(BaseModel):
    type: Literal["rectangle"] = "rectangle"
    x1_mm: float = 0.0
    y1_mm: float = 0.0
    x2_mm: float
    y2_mm: float


class CircleEntity(BaseModel):
    type: Literal["circle"] = "circle"
    cx_mm: float = 0.0
    cy_mm: float = 0.0
    radius_mm: float


class LineEntity(BaseModel):
    type: Literal["line"] = "line"
    x1_mm: float
    y1_mm: float
    x2_mm: float
    y2_mm: float


class ArcEntity(BaseModel):
    """
    Circular arc by centre + radius + start/end angles.
    Angles are measured CCW from the +X axis (standard math convention).
    clockwise=False → CCW arc (default for external profiles).
    clockwise=True  → CW arc (for internal cutouts, holes in profiles).

    C# executor: sketchMgr.CreateArc(cx,cy,0, xStart,yStart,0, xEnd,yEnd,0, dir)
    where dir = clockwise ? -1 : 1, xStart = cx + r*cos(start_angle_deg*π/180), etc.
    """
    type:            Literal["arc"] = "arc"
    cx_mm:           float
    cy_mm:           float
    radius_mm:       float
    start_angle_deg: float          # CCW from +X, degrees
    end_angle_deg:   float          # CCW from +X, degrees
    clockwise:       bool = False


SketchEntity = Annotated[
    Union[RectangleEntity, CircleEntity, LineEntity, ArcEntity],
    Field(discriminator="type"),
]


class NamedDimension(BaseModel):
    name:     str
    value_mm: float


class CreatePartOp(BaseModel):
    id:   str
    type: Literal["create_part"] = "create_part"


class CreateSketchOp(BaseModel):
    id:        str
    type:      Literal["create_sketch"] = "create_sketch"
    plane:     str = "Top Plane"
    sketch_id: str


class AddCenterRectangleOp(BaseModel):
    id:        str
    type:      Literal["add_center_rectangle"] = "add_center_rectangle"
    sketch_id: str
    center:    List[float] = Field(default_factory=lambda: [0.0, 0.0])
    length:    float
    width:     float
    units:     Literal["mm"] = "mm"

    @model_validator(mode="after")
    def _chk(self) -> "AddCenterRectangleOp":
        if len(self.center) != 2:
            raise ValueError("add_center_rectangle center must contain [x, y]")
        if self.length <= 0 or self.width <= 0:
            raise ValueError("add_center_rectangle length and width must be positive")
        return self


class CirclePrimitive(BaseModel):
    center:   List[float]
    diameter: float

    @model_validator(mode="after")
    def _chk(self) -> "CirclePrimitive":
        if len(self.center) != 2:
            raise ValueError("circle center must contain [x, y]")
        if self.diameter <= 0:
            raise ValueError("circle diameter must be positive")
        return self


class AddCirclesOp(BaseModel):
    id:        str
    type:      Literal["add_circles"] = "add_circles"
    sketch_id: str
    circles:   List[CirclePrimitive] = Field(default_factory=list)
    units:     Literal["mm"] = "mm"

    @model_validator(mode="after")
    def _chk(self) -> "AddCirclesOp":
        if not self.circles:
            raise ValueError("add_circles requires at least one circle")
        return self


class SketchOp(BaseModel):
    id:         str
    type:       Literal["sketch"] = "sketch"
    plane:      str                    = "Top Plane"
    entities:   List[SketchEntity]     = Field(default_factory=list)
    named_dims: List[NamedDimension]   = Field(default_factory=list)


class ExtrudeBossOp(BaseModel):
    id:           str
    type:         Literal["extrude_boss"] = "extrude_boss"
    profile_id:   Optional[str] = None
    sketch_id:    Optional[str] = None
    depth_mm:     Optional[float] = None
    depth:        Optional[float] = None
    name:         Optional[str] = None
    feature_name: Optional[str] = None
    direction:    Optional[str] = None

    @model_validator(mode="after")
    def _chk(self) -> "ExtrudeBossOp":
        if self.profile_id is None and self.sketch_id is not None:
            self.profile_id = self.sketch_id
        if self.depth_mm is None and self.depth is not None:
            self.depth_mm = self.depth
        if self.name is None and self.feature_name is not None:
            self.name = self.feature_name
        if not self.profile_id:
            raise ValueError("extrude_boss requires profile_id or sketch_id")
        if self.depth_mm is None or self.depth_mm <= 0:
            raise ValueError("extrude_boss depth_mm must be positive")
        return self


class ExtrudeCutOp(BaseModel):
    id:           str
    type:         Literal["extrude_cut"] = "extrude_cut"
    profile_id:   Optional[str] = None
    sketch_id:    Optional[str] = None
    depth_mm:     float = 0.0
    depth:        Optional[float] = None
    through_all:  bool = True
    cut_type:     Optional[str] = None
    name:         Optional[str] = None
    feature_name: Optional[str] = None

    @model_validator(mode="after")
    def _chk(self) -> "ExtrudeCutOp":
        if self.profile_id is None and self.sketch_id is not None:
            self.profile_id = self.sketch_id
        if self.depth is not None and self.depth_mm <= 0:
            self.depth_mm = self.depth
        if self.name is None and self.feature_name is not None:
            self.name = self.feature_name
        if self.cut_type == "through_all":
            self.through_all = True
        if not self.profile_id:
            raise ValueError("extrude_cut requires profile_id or sketch_id")
        return self


class RebuildOp(BaseModel):
    id:   str
    type: Literal["rebuild"] = "rebuild"


class FilletOp(BaseModel):
    id:          str
    type:        Literal["fillet"] = "fillet"
    feature_ids: List[str] = Field(default_factory=list)
    radius_mm:   float

    @model_validator(mode="after")
    def _chk(self) -> "FilletOp":
        if self.radius_mm <= 0:
            raise ValueError("fillet radius_mm must be positive")
        return self


class ChamferOp(BaseModel):
    id:          str
    type:        Literal["chamfer"] = "chamfer"
    feature_ids: List[str] = Field(default_factory=list)
    distance_mm: float

    @model_validator(mode="after")
    def _chk(self) -> "ChamferOp":
        if self.distance_mm <= 0:
            raise ValueError("chamfer distance_mm must be positive")
        return self


class HolePosition(BaseModel):
    x_mm: float
    y_mm: float


class HoleWizardOp(BaseModel):
    id:           str
    type:         Literal["hole_wizard"] = "hole_wizard"
    face_of:      str
    hole_type:    Literal["simple", "counterbore", "countersink", "tapped"] = "simple"
    fastener_size: str  = "M6"
    depth_mm:     float = 0.0
    through_all:  bool  = True
    positions:    List[HolePosition] = Field(default_factory=list)

    @model_validator(mode="after")
    def _chk(self) -> "HoleWizardOp":
        if not self.positions:
            raise ValueError("hole_wizard requires at least one position")
        return self


class CircularPatternOp(BaseModel):
    id:              str
    type:            Literal["circular_pattern"] = "circular_pattern"
    source_ids:      List[str]
    count:           int
    pcd_mm:          float
    axis_feature_id: Optional[str] = None

    @model_validator(mode="after")
    def _chk(self) -> "CircularPatternOp":
        if self.count < 2:
            raise ValueError("circular_pattern count must be >= 2")
        if self.pcd_mm <= 0:
            raise ValueError("circular_pattern pcd_mm must be positive")
        return self


class LinearPatternOp(BaseModel):
    id:              str
    type:            Literal["linear_pattern"] = "linear_pattern"
    source_ids:      List[str]
    dir1_count:      int   = 1
    dir1_spacing_mm: float = 0.0
    dir2_count:      int   = 1
    dir2_spacing_mm: float = 0.0


class MirrorOp(BaseModel):
    id:           str
    type:         Literal["mirror"] = "mirror"
    source_ids:   List[str]
    mirror_plane: str = "Right Plane"


class RevolveOp(BaseModel):
    id:         str
    type:       Literal["revolve"] = "revolve"
    profile_id: str
    angle_deg:  float = 360.0


class DeleteFeatureOp(BaseModel):
    id:          str
    type:        Literal["delete_feature"] = "delete_feature"
    feature_ids: List[str]    = Field(default_factory=list)
    last_n:      Optional[int] = None


class NoopOp(BaseModel):
    id:      str
    type:    Literal["noop"] = "noop"
    message: str = ""


class TitleBlockFields(BaseModel):
    revision:    Optional[str]       = None
    drawn_by:    Optional[str]       = None
    checked_by:  Optional[str]       = None
    title:       Optional[str]       = None
    description: Optional[str]       = None
    date:        Optional[str]       = None  # ISO date string e.g. "2026-05-15"
    custom:      dict[str, str]      = Field(default_factory=dict)


class UpdateTitleBlockOp(BaseModel):
    id:          str
    type:        Literal["update_title_block"] = "update_title_block"
    title_block: TitleBlockFields


class ExportFileConfig(BaseModel):
    format:            Literal["PDF", "DXF", "STEP", "IGES", "STL"]
    output_path:       Optional[str] = None
    filename_template: Optional[str] = None


class ExportFileOp(BaseModel):
    id:          str
    type:        Literal["export_file"] = "export_file"
    export_file: ExportFileConfig


class CheckDrawingOp(BaseModel):
    id:   str
    type: Literal["check_drawing"] = "check_drawing"


class GenerateMacroOp(BaseModel):
    id:          str
    type:        Literal["generate_macro"] = "generate_macro"
    description: str
    output_path: Optional[str] = None


Operation = Annotated[
    Union[
        CreatePartOp, CreateSketchOp, AddCenterRectangleOp, AddCirclesOp,
        SketchOp, ExtrudeBossOp, ExtrudeCutOp, RebuildOp,
        FilletOp, ChamferOp, HoleWizardOp,
        CircularPatternOp, LinearPatternOp, MirrorOp,
        RevolveOp, DeleteFeatureOp, NoopOp,
        UpdateTitleBlockOp, ExportFileOp, CheckDrawingOp, GenerateMacroOp,
    ],
    Field(discriminator="type"),
]


class OperationGraph(BaseModel):
    schema_version: str = "0.2"
    trace_id:       Optional[str]    = None
    part_family:    Optional[str]    = None
    part_name:      Optional[str]    = None
    reasoning:      Optional[str]    = None  # LLM scratchpad — dimension derivation notes
    operations:     List[Operation]
    missing_inputs: List[str]        = Field(default_factory=list)
    assumptions:    List[str]        = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_ids(self) -> "OperationGraph":
        ids = [op.id for op in self.operations]
        if len(ids) != len(set(ids)):
            raise ValueError("Operation IDs must be unique within the graph")
        return self


# ── API response ──────────────────────────────────────────────────────────────

class GenerateResponse(BaseModel):
    macro_code:      Optional[str]            = None
    cad_command:     Optional[CadCommand]     = None   # kept for test backward-compat
    operation_graph: Optional[OperationGraph] = None   # primary execution path
    design_spec:     Optional[DesignSpec]     = None
    coordinate_plan: Optional[CoordinatePlan] = None
    sketch_graph:    Optional[SketchGraph]    = None
    trace_id:        Optional[str]            = None
    run_artifact_path: Optional[str]          = None
    status_message:  str
    rag_sources:     list[str]                = Field(default_factory=list)


class IngestResponse(BaseModel):
    ingested_files: int
    total_chunks:   int
    detail:         dict[str, int]


# ── Post-execution part report (mirrors C# OperationExecutor.ExtractPartReport) ─

class PartFeatureInfo(BaseModel):
    name:       str
    type:       str
    suppressed: bool = False


class PartSketchInfo(BaseModel):
    name:         str
    entity_count: Optional[int] = None
    dimension_count: Optional[int] = None


class PartReport(BaseModel):
    document_type:  str                      = "part"
    rebuild_status: str                      = "success"
    body_count:     int
    bounding_box:   Optional[BoundingBox]    = None
    bounding_box_mm: Optional[BoundingBox]   = None
    mass_g:         Optional[float]          = None
    feature_count:  int                      = 0
    features:       List[PartFeatureInfo]    = Field(default_factory=list)
    sketches:       List[PartSketchInfo]     = Field(default_factory=list)


# ── Validation report (graph requested vs. report produced) ───────────────────

class Discrepancy(BaseModel):
    category: Literal[
        "bounding_box", "body_count", "feature_count",
        "missing_feature", "unexpected_feature", "suppressed_feature",
        "sketch_entity_count", "rebuild_status", "failed_operation",
    ]
    severity: Literal["info", "warning", "error"]
    expected: str
    actual:   str
    message:  str


class ValidationReport(BaseModel):
    passed:           bool
    has_warnings:     bool
    discrepancies:    List[Discrepancy] = Field(default_factory=list)
    expected_summary: dict              = Field(default_factory=dict)
    actual_summary:   dict              = Field(default_factory=dict)


class ValidateRequest(BaseModel):
    operation_graph: OperationGraph
    part_report:     PartReport
    executor_result: Optional[ExecutorRunResult] = None
    tolerance_mm:    float = 1.0
    trace_id:        Optional[str] = None  # links /validate back to /generate trace folder
