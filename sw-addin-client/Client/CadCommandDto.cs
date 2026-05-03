using Newtonsoft.Json;

namespace SwCopilotAddin.Client
{
    public struct DimensionsMetersDto
    {
        [JsonProperty("length")]
        public double? Length { get; set; }

        [JsonProperty("width")]
        public double? Width { get; set; }

        [JsonProperty("height")]
        public double? Height { get; set; }

        [JsonProperty("radius")]
        public double? Radius { get; set; }

        [JsonProperty("diameter")]
        public double? Diameter { get; set; }

        [JsonProperty("depth")]
        public double? Depth { get; set; }
    }

    /// <summary>
    /// Holds action-specific targeting data.
    /// delete_named:  feature_names populated.
    /// delete_last_n: last_n_count populated.
    /// </summary>
    public class TargetReferenceDto
    {
        [JsonProperty("feature_names")]
        public string[]? FeatureNames { get; set; }

        [JsonProperty("last_n_count")]
        public int? LastNCount { get; set; }
    }

    public struct CadCommandDto
    {
        [JsonProperty("action")]
        public string? Action { get; set; }

        [JsonProperty("shape_type")]
        public string? ShapeType { get; set; }

        [JsonProperty("dimensions_meters")]
        public DimensionsMetersDto DimensionsMeters { get; set; }

        [JsonProperty("target_plane")]
        public string? TargetPlane { get; set; }

        [JsonProperty("target_face")]
        public string? TargetFace { get; set; }

        /// <summary>
        /// delete_named:  {"feature_names": ["Boss-Extrude1"]}
        /// delete_last_n: {"last_n_count": 2}
        /// </summary>
        [JsonProperty("target_reference")]
        public TargetReferenceDto? TargetReference { get; set; }

        [JsonProperty("tolerance")]
        public double Tolerance { get; set; }

        [JsonProperty("clear_existing")]
        public bool ClearExisting { get; set; }

        [JsonProperty("message")]
        public string? Message { get; set; }
    }
}
