using Newtonsoft.Json;

namespace SwCopilotAddin.Client
{
    public sealed class OperationGraphDto
    {
        [JsonProperty("schema_version")]       public string?               SchemaVersion       { get; set; }
        [JsonProperty("trace_id")]             public string?               TraceId             { get; set; }
        [JsonProperty("part_family")]          public string?               PartFamily          { get; set; }
        [JsonProperty("part_name")]            public string?               PartName            { get; set; }
        [JsonProperty("reasoning")]            public string?               Reasoning           { get; set; }
        [JsonProperty("operations")]           public OperationDto[]        Operations          { get; set; } = System.Array.Empty<OperationDto>();
        [JsonProperty("missing_inputs")]       public string[]              MissingInputs       { get; set; } = System.Array.Empty<string>();
        [JsonProperty("assumptions")]          public string[]              Assumptions         { get; set; } = System.Array.Empty<string>();
        [JsonProperty("manufacturing_intent")] public ManufacturingIntentDto ManufacturingIntent { get; set; } = new ManufacturingIntentDto();
    }

    /// <summary>
    /// Flat DTO for every operation type.  Use the <see cref="Type"/> field to
    /// determine which optional fields are populated.
    /// </summary>
    public sealed class OperationDto
    {
        [JsonProperty("id")]   public string Id   { get; set; } = "";
        [JsonProperty("type")] public string Type { get; set; } = "";

        // ── sketch ────────────────────────────────────────────────────────────
        [JsonProperty("plane")]      public string?              Plane      { get; set; }
        [JsonProperty("sketch_id")]  public string?              SketchId   { get; set; }
        [JsonProperty("entities")]   public SketchEntityDto[]    Entities   { get; set; } = System.Array.Empty<SketchEntityDto>();
        [JsonProperty("named_dims")] public NamedDimDto[]        NamedDims  { get; set; } = System.Array.Empty<NamedDimDto>();
        [JsonProperty("relations")]  public SketchRelationDto[]  Relations  { get; set; } = System.Array.Empty<SketchRelationDto>();
        [JsonProperty("dimensions")] public SketchDimensionDto[] Dimensions { get; set; } = System.Array.Empty<SketchDimensionDto>();

        // v0.2 coordinate-first sketch primitives
        [JsonProperty("center")]  public double[]             Center     { get; set; } = System.Array.Empty<double>();
        [JsonProperty("length")]  public double?              Length     { get; set; }
        [JsonProperty("width")]   public double?              Width      { get; set; }
        [JsonProperty("circles")] public CirclePrimitiveDto[] Circles    { get; set; } = System.Array.Empty<CirclePrimitiveDto>();

        // ── extrude_boss / extrude_cut / revolve ──────────────────────────────
        [JsonProperty("profile_id")]  public string? ProfileId  { get; set; }
        [JsonProperty("depth_mm")]    public double? DepthMm    { get; set; }
        [JsonProperty("depth")]       public double? Depth      { get; set; }
        [JsonProperty("through_all")] public bool    ThroughAll { get; set; }
        [JsonProperty("name")]        public string? Name       { get; set; }
        [JsonProperty("feature_name")] public string? FeatureName { get; set; }
        [JsonProperty("cut_type")]    public string? CutType    { get; set; }
        [JsonProperty("direction")]   public string? Direction  { get; set; }
        [JsonProperty("angle_deg")]   public double? AngleDeg   { get; set; }

        // ── fillet / chamfer ──────────────────────────────────────────────────
        [JsonProperty("feature_ids")]  public string[] FeatureIds  { get; set; } = System.Array.Empty<string>();
        [JsonProperty("radius_mm")]    public double?  RadiusMm    { get; set; }
        [JsonProperty("distance_mm")]  public double?  DistanceMm  { get; set; }

        // ── hole_wizard ───────────────────────────────────────────────────────
        [JsonProperty("face_of")]       public string?          FaceOf       { get; set; }
        [JsonProperty("hole_type")]     public string?          HoleType     { get; set; }
        [JsonProperty("fastener_size")] public string?          FastenerSize { get; set; }
        [JsonProperty("positions")]     public HolePositionDto[] Positions   { get; set; } = System.Array.Empty<HolePositionDto>();

        // ── patterns / mirror ─────────────────────────────────────────────────
        [JsonProperty("source_ids")]       public string[] SourceIds       { get; set; } = System.Array.Empty<string>();
        [JsonProperty("count")]            public int?     Count           { get; set; }
        [JsonProperty("pcd_mm")]           public double?  PcdMm           { get; set; }
        [JsonProperty("dir1_count")]       public int?     Dir1Count       { get; set; }
        [JsonProperty("dir1_spacing_mm")]  public double?  Dir1SpacingMm   { get; set; }
        [JsonProperty("dir2_count")]       public int?     Dir2Count       { get; set; }
        [JsonProperty("dir2_spacing_mm")]  public double?  Dir2SpacingMm   { get; set; }
        [JsonProperty("mirror_plane")]     public string?  MirrorPlane     { get; set; }

        // ── delete_feature ───────────────────────────────────────────────────
        [JsonProperty("last_n")] public int? LastN { get; set; }

        // ── swept_boss ────────────────────────────────────────────────────────
        [JsonProperty("path_id")] public string? PathId { get; set; }

        // ── noop ──────────────────────────────────────────────────────────────
        [JsonProperty("message")] public string? Message { get; set; }

        // ── update_title_block ────────────────────────────────────────────────
        [JsonProperty("title_block")] public TitleBlockFieldsDto? TitleBlock { get; set; }

        // ── export_file ───────────────────────────────────────────────────────
        [JsonProperty("export_file")] public ExportFileDto? ExportFile { get; set; }

        // ── generate_macro ────────────────────────────────────────────────────
        [JsonProperty("generate_macro")] public GenerateMacroDto? GenerateMacro { get; set; }
    }

    public sealed class GenerateMacroDto
    {
        [JsonProperty("description")] public string? Description { get; set; }
        [JsonProperty("output_path")] public string? OutputPath  { get; set; }
    }

    public sealed class TitleBlockFieldsDto
    {
        [JsonProperty("revision")]    public string? Revision    { get; set; }
        [JsonProperty("drawn_by")]    public string? DrawnBy     { get; set; }
        [JsonProperty("checked_by")] public string? CheckedBy   { get; set; }
        [JsonProperty("title")]      public string? Title       { get; set; }
        [JsonProperty("description")] public string? Description { get; set; }
        [JsonProperty("date")]       public string? Date        { get; set; }
        [JsonProperty("custom")]     public System.Collections.Generic.Dictionary<string, string>? Custom { get; set; }
    }

    public sealed class ExportFileDto
    {
        [JsonProperty("format")]            public string? Format           { get; set; }
        [JsonProperty("output_path")]       public string? OutputPath       { get; set; }
        [JsonProperty("filename_template")] public string? FilenameTemplate { get; set; }
    }

    public sealed class SketchRelationDto
    {
        [JsonProperty("type")]       public string   Type      { get; set; } = "";
        [JsonProperty("entity_ids")] public string[] EntityIds { get; set; } = System.Array.Empty<string>();
        [JsonProperty("ref_id")]     public string?  RefId     { get; set; }
    }

    public sealed class SketchDimensionDto
    {
        [JsonProperty("type")]      public string  Type     { get; set; } = "";
        [JsonProperty("entity_id")] public string  EntityId { get; set; } = "";
        [JsonProperty("ref_id")]    public string? RefId    { get; set; }
        [JsonProperty("value_mm")]  public double  ValueMm  { get; set; }
    }

    public sealed class ManufacturingIntentDto
    {
        [JsonProperty("material")]        public string Material       { get; set; } = "steel";
        [JsonProperty("process")]         public string Process        { get; set; } = "machined";
        [JsonProperty("tolerance_class")] public string ToleranceClass { get; set; } = "medium";
    }

    public sealed class SketchEntityDto
    {
        [JsonProperty("id")]        public string  Id      { get; set; } = "";
        [JsonProperty("type")]      public string  Type    { get; set; } = "";

        // rectangle / line
        [JsonProperty("x1_mm")] public double? X1Mm { get; set; }
        [JsonProperty("y1_mm")] public double? Y1Mm { get; set; }
        [JsonProperty("x2_mm")] public double? X2Mm { get; set; }
        [JsonProperty("y2_mm")] public double? Y2Mm { get; set; }

        // circle
        [JsonProperty("cx_mm")]     public double? CxMm     { get; set; }
        [JsonProperty("cy_mm")]     public double? CyMm     { get; set; }
        [JsonProperty("radius_mm")] public double? RadiusMm { get; set; }
    }

    public sealed class NamedDimDto
    {
        [JsonProperty("name")]     public string Name    { get; set; } = "";
        [JsonProperty("value_mm")] public double ValueMm { get; set; }
    }

    public sealed class HolePositionDto
    {
        [JsonProperty("x_mm")] public double XMm { get; set; }
        [JsonProperty("y_mm")] public double YMm { get; set; }
    }

    public sealed class CirclePrimitiveDto
    {
        [JsonProperty("center")]   public double[] Center   { get; set; } = System.Array.Empty<double>();
        [JsonProperty("diameter")] public double?  Diameter { get; set; }
    }
}
