using Newtonsoft.Json;

namespace SwCopilotAddin.Client
{
    public sealed class OperationGraphDto
    {
        [JsonProperty("schema_version")] public string?        SchemaVersion { get; set; }
        [JsonProperty("part_name")]      public string?        PartName      { get; set; }
        [JsonProperty("operations")]     public OperationDto[] Operations    { get; set; } = System.Array.Empty<OperationDto>();
        [JsonProperty("missing_inputs")] public string[]       MissingInputs { get; set; } = System.Array.Empty<string>();
        [JsonProperty("assumptions")]    public string[]       Assumptions   { get; set; } = System.Array.Empty<string>();
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
        [JsonProperty("plane")]      public string?           Plane      { get; set; }
        [JsonProperty("entities")]   public SketchEntityDto[] Entities   { get; set; } = System.Array.Empty<SketchEntityDto>();
        [JsonProperty("named_dims")] public NamedDimDto[]     NamedDims  { get; set; } = System.Array.Empty<NamedDimDto>();

        // ── extrude_boss / extrude_cut / revolve ──────────────────────────────
        [JsonProperty("profile_id")]  public string? ProfileId  { get; set; }
        [JsonProperty("depth_mm")]    public double? DepthMm    { get; set; }
        [JsonProperty("through_all")] public bool    ThroughAll { get; set; }
        [JsonProperty("name")]        public string? Name       { get; set; }
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

        // ── noop ──────────────────────────────────────────────────────────────
        [JsonProperty("message")] public string? Message { get; set; }
    }

    public sealed class SketchEntityDto
    {
        [JsonProperty("type")]      public string Type    { get; set; } = "";

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
}
