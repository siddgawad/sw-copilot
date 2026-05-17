using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using Newtonsoft.Json;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;
using SwCopilotAddin.Client;

namespace SwCopilotAddin.Execution
{
    /// <summary>
    /// Executes an <see cref="OperationGraphDto"/> against the live SolidWorks document.
    /// Each operation type maps to a deterministic set of SolidWorks COM calls.
    /// </summary>
    public sealed class OperationExecutor
    {
        private readonly ISldWorks _swApp;

        // Operations register their created Feature here so later ops can reference them.
        private readonly Dictionary<string, Feature> _features =
            new Dictionary<string, Feature>(StringComparer.OrdinalIgnoreCase);

        private readonly List<Feature> _lastCreatedFeatures = new List<Feature>();
        private string? _activeSketchId;

        private static readonly HashSet<string> _systemTypes = new HashSet<string>
        {
            "RefPlane", "OriginProfileFeature", "Reference", "HistoryFolder",
            "SelectionSetFolder", "SensorFolder", "MaterialFolder",
            "CommentsFolder", "DesignBinder",
        };

        private enum DocumentRequirement
        {
            None,
            ActiveDocument,
            PartDocument,
            DrawingDocument,
        }

        public OperationExecutor(ISldWorks swApp)
        {
            _swApp = swApp;
        }

        private sealed class ExecutorOperationResult
        {
            [JsonProperty("operation_id")] public string OperationId { get; set; } = "";
            [JsonProperty("operation_type")] public string OperationType { get; set; } = "";
            [JsonProperty("status")] public string Status { get; set; } = "success";
            [JsonProperty("created_feature")] public string? CreatedFeature { get; set; }
            [JsonProperty("error_type")] public string? ErrorType { get; set; }
            [JsonProperty("message")] public string? Message { get; set; }
        }

        private sealed class ExecutorRunResult
        {
            [JsonProperty("status")] public string Status { get; set; } = "success";
            [JsonProperty("operations")] public List<ExecutorOperationResult> Operations { get; set; } =
                new List<ExecutorOperationResult>();
        }

        private sealed class SketchDefinitionResult
        {
            public int SmartDimensions { get; set; }
            public int Relations { get; set; }
            public int FullyDefineStatus { get; set; } = -1;

            public string Summary()
            {
                return $"smart dimensions={SmartDimensions}, relations={Relations}, fully_define_status={FullyDefineStatus}";
            }
        }

        public string Execute(OperationGraphDto graph)
        {
            if (!string.IsNullOrWhiteSpace(graph.SchemaVersion) &&
                !string.Equals(graph.SchemaVersion, "0.2", StringComparison.Ordinal))
            {
                return $"ERROR: Unsupported operation graph schema_version '{graph.SchemaVersion}'. Expected '0.2'.";
            }

            string? documentViolation = ValidateDocumentRequirements(graph);
            if (documentViolation != null)
                return documentViolation;

            DocumentRequirement requirement = GetDocumentRequirement(graph);
            IModelDoc2? doc = ResolveExecutionDocument(requirement);
            if (doc == null) return MissingDocumentMessage(requirement);

            var lines = new List<string>();

            if (!string.IsNullOrWhiteSpace(graph.PartName))
                lines.Add("Part: " + graph.PartName);

            if (graph.Assumptions?.Length > 0)
                lines.Add("Assumptions: " + string.Join("; ", graph.Assumptions));

            if (graph.MissingInputs?.Length > 0)
            {
                lines.Add("MISSING INPUTS — execution may be incomplete:");
                foreach (string m in graph.MissingInputs)
                    lines.Add("  • " + m);
            }

            // Pre-execution rule validation — catch geometric impossibilities before touching SW.
            string? ruleViolation = ValidateGraph(graph);
            if (ruleViolation != null)
            {
                var refused = new ExecutorRunResult
                {
                    Status = "failed",
                    Operations = new List<ExecutorOperationResult>(),
                };
                return $"RULE VIOLATION - execution refused:\n{ruleViolation}\n" +
                       "Runtime (executor_result): " + JsonConvert.SerializeObject(refused, Formatting.None);
            }

            _features.Clear();
            _lastCreatedFeatures.Clear();
            _activeSketchId = null;

            bool anyError = false;
            var opResults = new List<ExecutorOperationResult>();
            foreach (OperationDto op in graph.Operations ?? System.Array.Empty<OperationDto>())
            {
                string result;
                try
                {
                    result = doc == null
                        ? DispatchWithoutDocument(op)
                        : Dispatch(doc, op);
                }
                catch (Exception ex)
                {
                    result = "ERROR: " + ex.Message;
                }

                lines.Add($"[{op.Id}] {result}");
                bool failed = result.StartsWith("ERROR", StringComparison.OrdinalIgnoreCase) ||
                              result.StartsWith("Unknown operation", StringComparison.OrdinalIgnoreCase);
                opResults.Add(BuildOperationResult(op, result, failed));

                if (failed)
                {
                    anyError = true;
                    break;
                }
            }

            if (!anyError && doc != null && _activeSketchId != null)
            {
                string closeResult = CloseActiveSketch(doc, _activeSketchId);
                if (closeResult.StartsWith("ERROR", StringComparison.OrdinalIgnoreCase))
                    anyError = true;
            }

            if (!anyError && doc != null && RequiresFinalPartRebuild(graph))
                doc.ForceRebuild3(false);

            var runResult = new ExecutorRunResult
            {
                Status = anyError ? "failed" : "success",
                Operations = opResults,
            };
            lines.Add("Runtime (executor_result): " + JsonConvert.SerializeObject(runResult, Formatting.None));
            if (doc != null && doc.GetType() == (int)swDocumentTypes_e.swDocPART)
                lines.Add("Runtime (report): " + ExtractPartReport(doc));

            return string.Join("\n", lines);
        }

        public string RollbackLastExecute(IModelDoc2? doc = null)
        {
            doc ??= EnsurePartDoc(createIfMissing: false);
            if (doc == null) return "ERROR: No active part document.";

            if (_lastCreatedFeatures.Count == 0)
                return "No features available to undo.";

            doc.ClearSelection2(true);

            int selected = 0;
            foreach (Feature feature in _lastCreatedFeatures.AsEnumerable().Reverse())
            {
                try
                {
                    string name = feature.Name;
                    if (string.IsNullOrWhiteSpace(name))
                        continue;

                    if (feature.Select2(selected > 0, 0))
                        selected++;
                }
                catch
                {
                    // Feature may have been deleted manually since the last execution.
                }
            }

            if (selected == 0)
            {
                _lastCreatedFeatures.Clear();
                _features.Clear();
                return "No previously-created features could be selected for undo.";
            }

            int opts = (int)swDeleteSelectionOptions_e.swDelete_Absorbed |
                       (int)swDeleteSelectionOptions_e.swDelete_Children;
            doc.Extension.DeleteSelection2(opts);
            doc.ForceRebuild3(false);

            _lastCreatedFeatures.Clear();
            _features.Clear();

            string noun = selected == 1 ? "feature" : "features";
            return $"Undid last execution batch ({selected} {noun} deleted).";
        }

        private static string? ValidateDocumentRequirements(OperationGraphDto graph)
        {
            bool hasPartOperation = (graph.Operations ?? System.Array.Empty<OperationDto>())
                .Any(op => IsPartDocumentOperation(op.Type));
            bool hasDrawingOperation = (graph.Operations ?? System.Array.Empty<OperationDto>())
                .Any(op => IsDrawingDocumentOperation(op.Type));

            if (hasPartOperation && hasDrawingOperation)
            {
                return "ERROR: Operation graph mixes part-modeling operations with drawing-only operations. " +
                       "Run the part edit and drawing check as separate prompts.";
            }

            return null;
        }

        private static DocumentRequirement GetDocumentRequirement(OperationGraphDto graph)
        {
            OperationDto[] operations = graph.Operations ?? System.Array.Empty<OperationDto>();

            if (operations.Any(op => IsDrawingDocumentOperation(op.Type)))
                return DocumentRequirement.DrawingDocument;

            if (operations.Any(op => IsPartDocumentOperation(op.Type)))
                return DocumentRequirement.PartDocument;

            if (operations.Any(op => IsActiveDocumentOperation(op.Type)))
                return DocumentRequirement.ActiveDocument;

            return DocumentRequirement.None;
        }

        private IModelDoc2? ResolveExecutionDocument(DocumentRequirement requirement)
        {
            if (requirement == DocumentRequirement.None)
                return null;

            IModelDoc2? doc = (IModelDoc2?)_swApp.ActiveDoc;

            if (requirement == DocumentRequirement.PartDocument)
            {
                if (doc == null)
                {
                    _swApp.NewPart();
                    doc = (IModelDoc2?)_swApp.ActiveDoc;
                }

                return doc != null && doc.GetType() == (int)swDocumentTypes_e.swDocPART
                    ? doc
                    : null;
            }

            if (doc == null)
                return null;

            if (requirement == DocumentRequirement.DrawingDocument &&
                doc.GetType() != (int)swDocumentTypes_e.swDocDRAWING)
            {
                return null;
            }

            return doc;
        }

        private static string MissingDocumentMessage(DocumentRequirement requirement)
        {
            switch (requirement)
            {
                case DocumentRequirement.PartDocument:
                    return "ERROR: No active part document.";
                case DocumentRequirement.DrawingDocument:
                    return "ERROR: check_drawing requires an active drawing document";
                case DocumentRequirement.ActiveDocument:
                    return "ERROR: No active document.";
                default:
                    return "ERROR: No active document.";
            }
        }

        private static bool IsPartDocumentOperation(string? type)
        {
            switch ((type ?? "").Trim().ToLowerInvariant())
            {
                case "create_part":
                case "create_sketch":
                case "add_center_rectangle":
                case "add_circles":
                case "sketch":
                case "extrude_boss":
                case "extrude_cut":
                case "fillet":
                case "chamfer":
                case "hole_wizard":
                case "circular_pattern":
                case "linear_pattern":
                case "mirror":
                case "revolve":
                case "delete_feature":
                    return true;
                default:
                    return false;
            }
        }

        private static bool IsDrawingDocumentOperation(string? type)
        {
            return string.Equals(
                (type ?? "").Trim(),
                "check_drawing",
                StringComparison.OrdinalIgnoreCase);
        }

        private static bool IsActiveDocumentOperation(string? type)
        {
            switch ((type ?? "").Trim().ToLowerInvariant())
            {
                case "update_title_block":
                case "export_file":
                case "rebuild":
                    return true;
                default:
                    return false;
            }
        }

        private static bool RequiresFinalPartRebuild(OperationGraphDto graph)
        {
            return (graph.Operations ?? System.Array.Empty<OperationDto>())
                .Any(op => IsPartDocumentOperation(op.Type));
        }

        // ── Pre-execution rule engine ─────────────────────────────────────────
        // Returns a violation message, or null if the graph is valid.

        private static string? ValidateGraph(OperationGraphDto graph)
        {
            var violations = new System.Text.StringBuilder();

            foreach (OperationDto op in graph.Operations ?? System.Array.Empty<OperationDto>())
            {
                switch ((op.Type ?? "").ToLowerInvariant())
                {
                    case "extrude_boss":
                    case "extrude_cut":
                        if (!op.ThroughAll && (op.DepthMm ?? 0) <= 0)
                            violations.AppendLine($"[{op.Id}] depth_mm must be positive for non-through extrude.");
                        break;

                    case "fillet":
                        if ((op.RadiusMm ?? 0) <= 0)
                            violations.AppendLine($"[{op.Id}] fillet radius_mm must be positive.");
                        if ((op.RadiusMm ?? 0) > 50)
                            violations.AppendLine($"[{op.Id}] fillet radius_mm={op.RadiusMm:0.##} is implausibly large (>50 mm). Likely a unit error.");
                        break;

                    case "chamfer":
                        if ((op.DistanceMm ?? 0) <= 0)
                            violations.AppendLine($"[{op.Id}] chamfer distance_mm must be positive.");
                        break;

                    case "hole_wizard":
                        if (op.Positions == null || op.Positions.Length == 0)
                            violations.AppendLine($"[{op.Id}] hole_wizard requires at least one position.");
                        ValidateHolePatternGeometry(op, violations);
                        break;

                    case "circular_pattern":
                        if ((op.Count ?? 0) < 2)
                            violations.AppendLine($"[{op.Id}] circular_pattern count must be >= 2.");
                        if ((op.PcdMm ?? 0) <= 0)
                            violations.AppendLine($"[{op.Id}] circular_pattern pcd_mm must be positive.");
                        break;

                    case "revolve":
                        double angle = op.AngleDeg ?? 360.0;
                        if (angle <= 0 || angle > 360)
                            violations.AppendLine($"[{op.Id}] revolve angle_deg={angle:0.##} must be in (0, 360].");
                        break;

                    case "sketch":
                        foreach (SketchEntityDto e in op.Entities ?? System.Array.Empty<SketchEntityDto>())
                        {
                            if ((e.Type ?? "").ToLowerInvariant() == "circle" && (e.RadiusMm ?? 0) <= 0)
                                violations.AppendLine($"[{op.Id}] sketch circle has non-positive radius_mm.");
                            if ((e.Type ?? "").ToLowerInvariant() == "rectangle")
                            {
                                if (e.X1Mm == e.X2Mm || e.Y1Mm == e.Y2Mm)
                                    violations.AppendLine($"[{op.Id}] sketch rectangle has zero area (x1==x2 or y1==y2).");
                            }
                        }
                        break;
                }
            }

            string result = violations.ToString().Trim();
            return string.IsNullOrEmpty(result) ? null : result;
        }

        private static void ValidateHolePatternGeometry(OperationDto op, StringBuilder violations)
        {
            HolePositionDto[] positions = op.Positions ?? System.Array.Empty<HolePositionDto>();
            if (positions.Length == 0)
                return;

            string fastenerSize = op.FastenerSize ?? "M6";
            string holeType = op.HoleType ?? "simple";
            double holeDiameterMm = HoleDiameterMm(fastenerSize, holeType);

            for (int i = 0; i < positions.Length; i++)
            {
                HolePositionDto a = positions[i];
                if (double.IsNaN(a.XMm) || double.IsNaN(a.YMm) ||
                    double.IsInfinity(a.XMm) || double.IsInfinity(a.YMm))
                {
                    violations.AppendLine($"[{op.Id}] hole position {i + 1} has invalid coordinates.");
                }

                for (int j = i + 1; j < positions.Length; j++)
                {
                    HolePositionDto b = positions[j];
                    double dx = a.XMm - b.XMm;
                    double dy = a.YMm - b.YMm;
                    double spacing = Math.Sqrt(dx * dx + dy * dy);
                    if (spacing + 0.01 < holeDiameterMm)
                    {
                        violations.AppendLine(
                            $"[{op.Id}] hole positions {i + 1} and {j + 1} overlap: " +
                            $"center spacing {spacing:0.###} mm is less than required " +
                            $"{holeDiameterMm:0.###} mm for {fastenerSize} {holeType}.");
                    }
                }
            }
        }

        // ── Dispatcher ────────────────────────────────────────────────────────

        private ExecutorOperationResult BuildOperationResult(OperationDto op, string message, bool failed)
        {
            string? createdFeature = null;
            if (!failed && _features.TryGetValue(op.Id, out Feature feature))
            {
                try { createdFeature = feature.Name; } catch { }
            }

            return new ExecutorOperationResult
            {
                OperationId = op.Id,
                OperationType = op.Type,
                Status = failed ? "failed" : "success",
                CreatedFeature = createdFeature,
                ErrorType = failed ? ClassifyError(message) : null,
                Message = string.IsNullOrWhiteSpace(message) ? null : message,
            };
        }

        private static string ClassifyError(string message)
        {
            if (message.IndexOf("sketch", StringComparison.OrdinalIgnoreCase) >= 0)
                return "SKETCH_PROFILE_INVALID";
            if (message.IndexOf("select", StringComparison.OrdinalIgnoreCase) >= 0)
                return "SELECTION_FAILED";
            if (message.IndexOf("cut", StringComparison.OrdinalIgnoreCase) >= 0)
                return "CUT_FAILED";
            if (message.IndexOf("extrude", StringComparison.OrdinalIgnoreCase) >= 0)
                return "EXTRUDE_FAILED";
            return "EXECUTION_FAILED";
        }

        private static string DispatchWithoutDocument(OperationDto op)
        {
            switch ((op.Type ?? "").Trim().ToLowerInvariant())
            {
                case "noop":
                    return op.Message ?? "No operation.";
                default:
                    return "ERROR: No active document.";
            }
        }

        private string Dispatch(IModelDoc2 doc, OperationDto op)
        {
            switch ((op.Type ?? "").Trim().ToLowerInvariant())
            {
                case "create_part":       return ExecCreatePart(doc);
                case "create_sketch":     return ExecCreateSketch(doc, op);
                case "add_center_rectangle": return ExecAddCenterRectangle(doc, op);
                case "add_circles":       return ExecAddCircles(doc, op);
                case "sketch":            return ExecSketch(doc, op);
                case "extrude_boss":      return ExecExtrudeBoss(doc, op);
                case "extrude_cut":       return ExecExtrudeCut(doc, op);
                case "fillet":            return ExecFillet(doc, op);
                case "chamfer":           return ExecChamfer(doc, op);
                case "hole_wizard":       return ExecHoleWizard(doc, op);
                case "circular_pattern":  return ExecCircularPattern(doc, op);
                case "linear_pattern":    return ExecLinearPattern(doc, op);
                case "mirror":            return ExecMirror(doc, op);
                case "revolve":           return ExecRevolve(doc, op);
                case "delete_feature":    return ExecDeleteFeature(doc, op);
                case "update_title_block": return ExecUpdateTitleBlock(doc, op);
                case "export_file":       return ExecExportFile(doc, op);
                case "check_drawing":     return ExecCheckDrawing(doc, op);
                case "rebuild":           doc.ForceRebuild3(false); return "Rebuild";
                case "noop":              return op.Message ?? "No operation.";
                default:                  return $"Unknown operation type: {op.Type}";
            }
        }

        // ── sketch ────────────────────────────────────────────────────────────

        private string ExecCreatePart(IModelDoc2 doc)
        {
            return "Part document ready";
        }

        private string ExecCreateSketch(IModelDoc2 doc, OperationDto op)
        {
            string sketchId = op.SketchId ?? op.Id;
            if (_activeSketchId != null)
            {
                string close = CloseActiveSketch(doc, _activeSketchId);
                if (close.StartsWith("ERROR", StringComparison.OrdinalIgnoreCase))
                    return close;
            }

            string plane = op.Plane ?? "Top Plane";
            if (!SelectPlaneOrFace(doc, plane))
                return $"ERROR: Could not select '{plane}'";

            doc.SketchManager.InsertSketch(true);
            _activeSketchId = sketchId;
            return $"Create sketch '{sketchId}' on {plane}";
        }

        private string ExecAddCenterRectangle(IModelDoc2 doc, OperationDto op)
        {
            if (!IsActiveSketch(op.SketchId))
                return $"ERROR: add_center_rectangle requires active sketch '{op.SketchId}'";
            if ((op.Length ?? 0) <= 0 || (op.Width ?? 0) <= 0)
                return "ERROR: add_center_rectangle length and width must be positive";

            double cx = op.Center.Length > 0 ? op.Center[0] : 0.0;
            double cy = op.Center.Length > 1 ? op.Center[1] : 0.0;
            double halfLength = (op.Length ?? 0) / 2.0;
            double halfWidth  = (op.Width  ?? 0) / 2.0;

            // CreateCenterRectangle produces a proper centre point for constraining.
            doc.SketchManager.CreateCenterRectangle(
                Mm(cx), Mm(cy), 0,
                Mm(cx + halfLength), Mm(cy + halfWidth), 0);

            SketchDefinitionResult definition = FullyDefineRectangle(doc, cx, cy, halfLength, halfWidth);

            return $"Center rectangle {op.Length:0.#} x {op.Width:0.#} mm ({definition.Summary()})";
        }

        /// <summary>
        /// Adds driving dimensions and an origin-coincident constraint so the sketch
        /// goes from blue (underdefined) to black (fully defined).
        /// Failures are intentionally swallowed — geometry is correct regardless.
        /// </summary>
        private SketchDefinitionResult FullyDefineRectangle(IModelDoc2 doc, double cx, double cy,
                                                            double halfLength, double halfWidth)
        {
            var result = new SketchDefinitionResult();
            try
            {
                result.Relations += TryConstrainSketchPointToOrigin(doc, cx, cy);

                // ── Width dimension (horizontal) ─────────────────────────────────
                // Select the bottom horizontal line at its midpoint.
                if (TryAddHorizontalSmartDimension(doc, cx, cy - halfWidth, cx, cy - halfWidth - 12))
                    result.SmartDimensions++;

                // ── Height dimension (vertical) ──────────────────────────────────
                // Select the left vertical line at its midpoint.
                if (TryAddVerticalSmartDimension(doc, cx - halfLength, cy, cx - halfLength - 12, cy))
                    result.SmartDimensions++;

                result.FullyDefineStatus = TryFullyDefineActiveSketch(doc);
            }
            catch
            {
                // Dimension/constraint failures never block execution.
                // Geometry is already correct; sketch may remain underdefined.
            }

            doc.ClearSelection2(true);
            return result;
        }

        private string ExecAddCircles(IModelDoc2 doc, OperationDto op)
        {
            if (!IsActiveSketch(op.SketchId))
                return $"ERROR: add_circles requires active sketch '{op.SketchId}'";
            if (op.Circles == null || op.Circles.Length == 0)
                return "ERROR: add_circles requires at least one circle";

            var definition = new SketchDefinitionResult();
            foreach (CirclePrimitiveDto circle in op.Circles)
            {
                if ((circle.Diameter ?? 0) <= 0)
                    return "ERROR: circle diameter must be positive";
                double cx = circle.Center.Length > 0 ? circle.Center[0] : 0.0;
                double cy = circle.Center.Length > 1 ? circle.Center[1] : 0.0;
                SketchSegment circleSegment = doc.SketchManager.CreateCircleByRadius(
                    Mm(cx), Mm(cy), 0, Mm(circle.Diameter / 2.0));

                if (TryAddDiameterSmartDimension(doc, circleSegment, cx, cy, circle.Diameter ?? 0))
                    definition.SmartDimensions++;

                SketchDefinitionResult centerDefinition = TryDefineCircleCenter(doc, circleSegment, cx, cy);
                definition.SmartDimensions += centerDefinition.SmartDimensions;
                definition.Relations += centerDefinition.Relations;
            }

            definition.FullyDefineStatus = TryFullyDefineActiveSketch(doc);
            doc.ClearSelection2(true);
            return $"Added {op.Circles.Length} circle(s) ({definition.Summary()})";
        }

        private static bool TryAddHorizontalSmartDimension(
            IModelDoc2 doc,
            double selectXmm,
            double selectYmm,
            double labelXmm,
            double labelYmm)
        {
            try
            {
                doc.ClearSelection2(true);
                bool selected = doc.Extension.SelectByID2(
                    "", "SKETCHSEGMENT",
                    Mm(selectXmm), Mm(selectYmm), 0,
                    false, 0, null, 0);
                if (!selected) return false;

                DisplayDimension? dim = doc.IAddHorizontalDimension2(Mm(labelXmm), Mm(labelYmm), 0);
                doc.ClearSelection2(true);
                return dim != null;
            }
            catch
            {
                doc.ClearSelection2(true);
                return false;
            }
        }

        private static bool TryAddVerticalSmartDimension(
            IModelDoc2 doc,
            double selectXmm,
            double selectYmm,
            double labelXmm,
            double labelYmm)
        {
            try
            {
                doc.ClearSelection2(true);
                bool selected = doc.Extension.SelectByID2(
                    "", "SKETCHSEGMENT",
                    Mm(selectXmm), Mm(selectYmm), 0,
                    false, 0, null, 0);
                if (!selected) return false;

                DisplayDimension? dim = doc.IAddVerticalDimension2(Mm(labelXmm), Mm(labelYmm), 0);
                doc.ClearSelection2(true);
                return dim != null;
            }
            catch
            {
                doc.ClearSelection2(true);
                return false;
            }
        }

        private static bool TryAddDiameterSmartDimension(
            IModelDoc2 doc,
            SketchSegment? circleSegment,
            double cxMm,
            double cyMm,
            double diameterMm)
        {
            if (circleSegment == null) return false;

            try
            {
                doc.ClearSelection2(true);
                bool selected = circleSegment.Select4(false, null);
                if (!selected)
                    selected = circleSegment.Select2(false, 0);
                if (!selected) return false;

                double radiusMm = diameterMm / 2.0;
                DisplayDimension? dim = doc.IAddDiameterDimension2(
                    Mm(cxMm + radiusMm + 10.0),
                    Mm(cyMm + radiusMm + 10.0),
                    0);
                doc.ClearSelection2(true);
                return dim != null;
            }
            catch
            {
                doc.ClearSelection2(true);
                return false;
            }
        }

        private static SketchDefinitionResult TryDefineCircleCenter(
            IModelDoc2 doc,
            SketchSegment? circleSegment,
            double cxMm,
            double cyMm)
        {
            var result = new SketchDefinitionResult();
            SketchPoint? center = GetCircleCenterPoint(circleSegment);
            if (center == null)
                return result;

            if (Math.Abs(cxMm) <= 1e-9 && Math.Abs(cyMm) <= 1e-9)
            {
                result.Relations += TryConstrainSketchPointToOrigin(doc, center);
                return result;
            }

            if (TryAddHorizontalPointToOriginDimension(doc, center, cxMm, cyMm))
                result.SmartDimensions++;
            if (TryAddVerticalPointToOriginDimension(doc, center, cxMm, cyMm))
                result.SmartDimensions++;
            return result;
        }

        private static SketchPoint? GetCircleCenterPoint(SketchSegment? circleSegment)
        {
            try
            {
                SketchArc? arc = circleSegment as SketchArc;
                return arc?.GetCenterPoint2() as SketchPoint;
            }
            catch
            {
                return null;
            }
        }

        private static int TryConstrainSketchPointToOrigin(IModelDoc2 doc, double xMm, double yMm)
        {
            try
            {
                doc.ClearSelection2(true);
                bool pointSelected = doc.Extension.SelectByID2(
                    "", "SKETCHPOINT",
                    Mm(xMm), Mm(yMm), 0,
                    false, 0, null, 0);
                if (!pointSelected) return 0;

                if (!TrySelectOriginPoint(doc, append: true))
                    return 0;

                doc.SketchAddConstraints("sgCOINCIDENT");
                doc.ClearSelection2(true);
                return 1;
            }
            catch
            {
                doc.ClearSelection2(true);
                return 0;
            }
        }

        private static int TryConstrainSketchPointToOrigin(IModelDoc2 doc, SketchPoint point)
        {
            try
            {
                doc.ClearSelection2(true);
                bool pointSelected = point.Select4(false, null) || point.Select2(false, 0);
                if (!pointSelected) return 0;

                if (!TrySelectOriginPoint(doc, append: true))
                    return 0;

                doc.SketchAddConstraints("sgCOINCIDENT");
                doc.ClearSelection2(true);
                return 1;
            }
            catch
            {
                doc.ClearSelection2(true);
                return 0;
            }
        }

        private static bool TryAddHorizontalPointToOriginDimension(
            IModelDoc2 doc,
            SketchPoint point,
            double cxMm,
            double cyMm)
        {
            try
            {
                doc.ClearSelection2(true);
                bool pointSelected = point.Select4(false, null) || point.Select2(false, 0);
                if (!pointSelected || !TrySelectOriginPoint(doc, append: true))
                    return false;

                DisplayDimension? dim = doc.IAddHorizontalDimension2(Mm(cxMm / 2.0), Mm(cyMm - 12.0), 0);
                doc.ClearSelection2(true);
                return dim != null;
            }
            catch
            {
                doc.ClearSelection2(true);
                return false;
            }
        }

        private static bool TryAddVerticalPointToOriginDimension(
            IModelDoc2 doc,
            SketchPoint point,
            double cxMm,
            double cyMm)
        {
            try
            {
                doc.ClearSelection2(true);
                bool pointSelected = point.Select4(false, null) || point.Select2(false, 0);
                if (!pointSelected || !TrySelectOriginPoint(doc, append: true))
                    return false;

                DisplayDimension? dim = doc.IAddVerticalDimension2(Mm(cxMm - 12.0), Mm(cyMm / 2.0), 0);
                doc.ClearSelection2(true);
                return dim != null;
            }
            catch
            {
                doc.ClearSelection2(true);
                return false;
            }
        }

        private static bool TrySelectOriginPoint(IModelDoc2 doc, bool append)
        {
            return doc.Extension.SelectByID2(
                       "Point1@Origin", "EXTSKETCHPOINT",
                       0, 0, 0,
                       append, 0, null, 0)
                   || doc.Extension.SelectByID2(
                       "Origin", "EXTSKETCHPOINT",
                       0, 0, 0,
                       append, 0, null, 0);
        }

        private static int TryFullyDefineActiveSketch(IModelDoc2 doc)
        {
            try
            {
                const int relationMask =
                    (int)swSketchFullyDefineRelationType_e.swSketchFullyDefineRelationType_Horizontal |
                    (int)swSketchFullyDefineRelationType_e.swSketchFullyDefineRelationType_Vertical |
                    (int)swSketchFullyDefineRelationType_e.swSketchFullyDefineRelationType_Coincident |
                    (int)swSketchFullyDefineRelationType_e.swSketchFullyDefineRelationType_Concentric;

                // Mirrors the official SOLIDWORKS API example: baseline dimensions,
                // null datums, below/right placement. Return value is not documented.
                return doc.SketchManager.FullyDefineSketch(
                    true,
                    true,
                    relationMask,
                    true,
                    1,
                    null,
                    1,
                    null,
                    1,
                    1);
            }
            catch
            {
                return -1;
            }
        }

        private string ExecSketch(IModelDoc2 doc, OperationDto op)
        {
            string plane = op.Plane ?? "Top Plane";

            if (!SelectPlaneOrFace(doc, plane))
                return $"ERROR: Could not select '{plane}'";

            SketchManager skMgr = doc.SketchManager;
            skMgr.InsertSketch(true);

            int drawn = 0;
            foreach (SketchEntityDto e in op.Entities ?? System.Array.Empty<SketchEntityDto>())
            {
                switch ((e.Type ?? "").ToLowerInvariant())
                {
                    case "rectangle":
                        skMgr.CreateCornerRectangle(
                            Mm(e.X1Mm), Mm(e.Y1Mm), 0,
                            Mm(e.X2Mm), Mm(e.Y2Mm), 0);
                        drawn++;
                        break;

                    case "circle":
                        double r = Mm(e.RadiusMm);
                        if (r <= 0) return "ERROR: circle radius_mm must be positive";
                        skMgr.CreateCircleByRadius(Mm(e.CxMm), Mm(e.CyMm), 0, r);
                        drawn++;
                        break;

                    case "line":
                        skMgr.CreateLine(
                            Mm(e.X1Mm), Mm(e.Y1Mm), 0,
                            Mm(e.X2Mm), Mm(e.Y2Mm), 0);
                        drawn++;
                        break;
                }
            }

            int fullyDefineStatus = TryFullyDefineActiveSketch(doc);
            skMgr.InsertSketch(true); // close sketch

            // Register the last sketch feature so later ops can reference this op id.
            Feature? sketchFeat = FindLastFeatureOfType(doc, "ProfileFeature", "3DProfileFeature");
            if (sketchFeat != null)
                RegisterFeature(op.Id, sketchFeat);

            return $"Sketch on {plane} with {drawn} entities (fully_define_status={fullyDefineStatus})";
        }

        // ── extrude_boss ──────────────────────────────────────────────────────

        private string ExecExtrudeBoss(IModelDoc2 doc, OperationDto op)
        {
            string? profileId = op.ProfileId ?? op.SketchId;
            if (string.IsNullOrEmpty(profileId))
                return "ERROR: extrude_boss requires profile_id";

            if (IsActiveSketch(profileId))
            {
                string close = CloseActiveSketch(doc, profileId!);
                if (close.StartsWith("ERROR", StringComparison.OrdinalIgnoreCase))
                    return close;
            }

            double depth = Mm(op.DepthMm ?? op.Depth);
            if (depth <= 0) return "ERROR: extrude_boss depth_mm must be positive";

            SelectRegisteredFeature(doc, profileId!);

            Feature? feature = doc.FeatureManager.FeatureExtrusion2(
                true, false, false,
                (int)swEndConditions_e.swEndCondBlind, 0,
                depth, 0.0,
                false, false, false, false,
                0.0, 0.0,
                false, false, false, false,
                true, true, true,
                0, 0.0, false);

            if (feature == null) return "ERROR: Extrude Boss failed — check sketch is closed";

            string? featureName = op.FeatureName ?? op.Name;
            if (!string.IsNullOrWhiteSpace(featureName))
                try { feature.Name = featureName; } catch { }

            RegisterFeature(op.Id, feature);
            doc.ForceRebuild3(false);
            return $"Extrude Boss {(op.DepthMm ?? op.Depth):0.#} mm";
        }

        // ── extrude_cut ───────────────────────────────────────────────────────

        private string ExecExtrudeCut(IModelDoc2 doc, OperationDto op)
        {
            string? profileId = op.ProfileId ?? op.SketchId;
            if (string.IsNullOrEmpty(profileId))
                return "ERROR: extrude_cut requires profile_id";

            if (IsActiveSketch(profileId))
            {
                string close = CloseActiveSketch(doc, profileId!);
                if (close.StartsWith("ERROR", StringComparison.OrdinalIgnoreCase))
                    return close;
            }

            SelectRegisteredFeature(doc, profileId!);

            bool thruAll = op.ThroughAll ||
                            string.Equals(op.CutType, "through_all", StringComparison.OrdinalIgnoreCase) ||
                            ((op.DepthMm ?? op.Depth ?? 0) <= 0);
            double depth = Mm(op.DepthMm ?? op.Depth);
            int endCond = thruAll
                ? (int)swEndConditions_e.swEndCondThroughAll
                : (int)swEndConditions_e.swEndCondBlind;

            Feature? feature = doc.FeatureManager.FeatureCut3(
                true, false, false,
                endCond,
                (int)swEndConditions_e.swEndCondBlind,
                depth, 0.0,
                false, false, false, false,
                0.0, 0.0,
                false, false, false, false,
                false, true, true, true, true, false,
                0, 0.0, false);

            if (feature == null) return "ERROR: Extrude Cut failed";

            string? featureName = op.FeatureName ?? op.Name;
            if (!string.IsNullOrWhiteSpace(featureName))
                try { feature.Name = featureName; } catch { }

            RegisterFeature(op.Id, feature);
            doc.ForceRebuild3(false);
            return thruAll ? "Extrude Cut through all" : $"Extrude Cut {(op.DepthMm ?? op.Depth):0.#} mm";
        }

        // ── fillet ────────────────────────────────────────────────────────────

        private string ExecFillet(IModelDoc2 doc, OperationDto op)
        {
            double radius = Mm(op.RadiusMm);
            if (radius <= 0) return "ERROR: fillet radius_mm must be positive";

            doc.ClearSelection2(true);

            bool anySelected = SelectEdgesForFillet(doc, op.FeatureIds);
            if (!anySelected) return "ERROR: No edges found to fillet";

            // FeatureFillet(Options, R1, Ftyp, OverflowType, Radii, SetBackDistances, PointRadiusArray)
            Feature? fillet = (Feature)doc.FeatureManager.FeatureFillet(
                0,                       // Options: 0 = none
                radius,                  // R1
                0,                       // Ftyp: 0 = constant radius
                0,                       // OverflowType: 0 = default
                new object[] { radius }, // Radii
                new object[] { },        // SetBackDistances
                new object[] { });       // PointRadiusArray

            if (fillet == null) return "ERROR: Fillet failed — try specifying only external edges or a smaller radius";

            RegisterFeature(op.Id, fillet);
            return $"Fillet R={op.RadiusMm:0.#} mm";
        }

        // ── chamfer ───────────────────────────────────────────────────────────

        private string ExecChamfer(IModelDoc2 doc, OperationDto op)
        {
            double dist = Mm(op.DistanceMm);
            if (dist <= 0) return "ERROR: chamfer distance_mm must be positive";

            doc.ClearSelection2(true);

            bool anySelected = SelectEdgesForFillet(doc, op.FeatureIds);
            if (!anySelected) return "ERROR: No edges found to chamfer";

            // InsertFeatureChamfer(Options, ChamferType, Width, Angle, OtherDist, VChamDist1, VChamDist2, VChamDist3)
            Feature? chamfer = (Feature)doc.FeatureManager.InsertFeatureChamfer(
                0,    // Options: 0 = none
                0,    // ChamferType: 0 = equal distance
                dist, // Width
                0.0,  // Angle (unused for equal-distance)
                0.0,  // OtherDist
                0.0,  // VertexChamDist1
                0.0,  // VertexChamDist2
                0.0); // VertexChamDist3

            if (chamfer == null) return "ERROR: Chamfer failed";

            RegisterFeature(op.Id, chamfer);
            return $"Chamfer {op.DistanceMm:0.#} mm";
        }

        // ── hole_wizard ───────────────────────────────────────────────────────
        // Implemented as sketch circles + extrude cut for reliability across SW versions.
        // Full Hole Wizard API (counterbore/CSink/tapped) is a v2 enhancement.

        private string ExecHoleWizard(IModelDoc2 doc, OperationDto op)
        {
            if (string.IsNullOrEmpty(op.FaceOf))
                return "ERROR: hole_wizard requires face_of";

            HolePositionDto[] positions = op.Positions ?? System.Array.Empty<HolePositionDto>();
            if (positions.Length == 0)
                return "ERROR: hole_wizard requires at least one position";

            string fastenerSize = op.FastenerSize ?? "M6";
            string holeType = (op.HoleType ?? "simple").ToLowerInvariant();
            string faceOf = op.FaceOf!;

            if (holeType == "counterbore")
            {
                string? clearanceError = CreateHoleCut(
                    doc,
                    op.Id + "_clearance",
                    faceOf,
                    positions,
                    ClearanceHoleDiameterMm(fastenerSize),
                    throughAll: true,
                    depthMm: 0.0,
                    out SketchDefinitionResult clearanceDefinition);
                if (clearanceError != null) return clearanceError;

                double counterboreDiameter = CounterboreDiameterMm(fastenerSize);
                double counterboreDepth = CounterboreDepthMm(fastenerSize);
                string? counterboreError = CreateHoleCut(
                    doc,
                    op.Id,
                    faceOf,
                    positions,
                    counterboreDiameter,
                    throughAll: false,
                    depthMm: counterboreDepth,
                    out SketchDefinitionResult counterboreDefinition);
                if (counterboreError != null) return counterboreError;

                return $"{positions.Length}x {fastenerSize} counterbore hole(s) " +
                       $"(clearance dia {ClearanceHoleDiameterMm(fastenerSize):0.###} mm through, " +
                       $"counterbore dia {counterboreDiameter:0.###} mm x {counterboreDepth:0.###} mm deep; " +
                       $"clearance {clearanceDefinition.Summary()}; counterbore {counterboreDefinition.Summary()})";
            }

            bool thruAll = op.ThroughAll || (op.DepthMm ?? 0) <= 0;
            double depthMm = op.DepthMm ?? 0.0;
            string? cutError = CreateHoleCut(
                doc,
                op.Id,
                faceOf,
                positions,
                HoleDiameterMm(fastenerSize, holeType),
                thruAll,
                depthMm,
                out SketchDefinitionResult definition);
            if (cutError != null) return cutError;

            string label = holeType == "simple" ? "drill" : holeType;
            return $"{positions.Length}x {fastenerSize} {label} hole(s) ({definition.Summary()})";
        }

        private string? CreateHoleCut(
            IModelDoc2 doc,
            string featureId,
            string faceOf,
            HolePositionDto[] positions,
            double holeDiameterMm,
            bool throughAll,
            double depthMm,
            out SketchDefinitionResult definition)
        {
            definition = new SketchDefinitionResult();
            double holeRadius = holeDiameterMm / 2.0 / 1000.0; // to metres

            // Resolve a standard plane directly, otherwise choose the highest
            // horizontal planar face from feature/body geometry.
            bool planeReady = SelectHoleSketchReference(doc, faceOf);

            if (!planeReady)
                return $"ERROR: Could not select sketch plane for holes (face_of='{faceOf}')";

            // Draw all hole circles in one sketch.
            SketchManager skMgr = doc.SketchManager;
            skMgr.InsertSketch(true);

            foreach (HolePositionDto pos in positions)
            {
                SketchSegment circleSegment = skMgr.CreateCircleByRadius(pos.XMm / 1000.0, pos.YMm / 1000.0, 0, holeRadius);
                if (TryAddDiameterSmartDimension(doc, circleSegment, pos.XMm, pos.YMm, holeDiameterMm))
                    definition.SmartDimensions++;
                SketchDefinitionResult centerDefinition = TryDefineCircleCenter(doc, circleSegment, pos.XMm, pos.YMm);
                definition.SmartDimensions += centerDefinition.SmartDimensions;
                definition.Relations += centerDefinition.Relations;
            }

            definition.FullyDefineStatus = TryFullyDefineActiveSketch(doc);
            skMgr.InsertSketch(true);

            double depth = Mm(depthMm);
            int endCond = throughAll
                ? (int)swEndConditions_e.swEndCondThroughAll
                : (int)swEndConditions_e.swEndCondBlind;

            Feature? cut = doc.FeatureManager.FeatureCut3(
                true, false, false,
                endCond,
                (int)swEndConditions_e.swEndCondBlind,
                depth, 0.0,
                false, false, false, false,
                0.0, 0.0,
                false, false, false, false,
                false, true, true, true, true, false,
                0, 0.0, false);

            if (cut == null) return "ERROR: Hole cut failed";

            RegisterFeature(featureId, cut);
            doc.ForceRebuild3(false);
            return null;
        }

        // ── circular_pattern ─────────────────────────────────────────────────

        private string ExecCircularPattern(IModelDoc2 doc, OperationDto op)
        {
            if (op.SourceIds == null || op.SourceIds.Length == 0)
                return "ERROR: circular_pattern requires source_ids";

            int count = op.Count ?? 2;
            if (count < 2) return "ERROR: circular_pattern count must be >= 2";

            doc.ClearSelection2(true);

            // Select the temporary axis (Z-axis at origin).
            bool axisSelected = doc.Extension.SelectByID2(
                "Temporary Axis", "AXIS", 0, 0, 0, false, 0, null, 0);

            if (!axisSelected)
            {
                // Try the origin axis by coordinate pick.
                axisSelected = doc.Extension.SelectByID2(
                    "", "AXIS", 0, 0, 0, false, 0, null, 0);
            }

            // Select source features with mark=4 (pattern seed).
            foreach (string sid in op.SourceIds)
            {
                if (_features.TryGetValue(sid, out Feature src))
                    src.Select2(true, 4);
            }

            double totalAngle = Math.PI * 2; // 360°

            // FeatureCircularPattern3(Number, Spacing, FlipDirection, DName, GeometryPattern, EqualSpacing)
            Feature? pattern;
            try
            {
                pattern = doc.FeatureManager.FeatureCircularPattern3(
                    count,      // Number
                    totalAngle, // Spacing (2π = full 360° when EqualSpacing=true)
                    false,      // FlipDirection
                    "D1",       // DName
                    false,      // GeometryPattern
                    true);      // EqualSpacing
            }
            catch
            {
                return "ERROR: Circular pattern failed — ensure an axis is selected";
            }

            if (pattern == null) return "ERROR: Circular pattern failed — ensure an axis is available";

            RegisterFeature(op.Id, pattern);
            return $"Circular pattern: {count}× on Ø{op.PcdMm:0.#} mm PCD";
        }

        // ── linear_pattern ───────────────────────────────────────────────────

        private string ExecLinearPattern(IModelDoc2 doc, OperationDto op)
        {
            if (op.SourceIds == null || op.SourceIds.Length == 0)
                return "ERROR: linear_pattern requires source_ids";

            int d1Count = op.Dir1Count ?? 1;
            int d2Count = op.Dir2Count ?? 1;
            double d1Spacing = Mm(op.Dir1SpacingMm);
            double d2Spacing = Mm(op.Dir2SpacingMm);

            doc.ClearSelection2(true);

            // Select a linear edge as the pattern direction (first long edge of bounding box).
            doc.Extension.SelectByID2("Right Plane", "PLANE", 0, 0, 0, false, 1, null, 0);

            foreach (string sid in op.SourceIds)
            {
                if (_features.TryGetValue(sid, out Feature src))
                    src.Select2(true, 4);
            }

            // FeatureLinearPattern3(Num1, Spacing1, Num2, Spacing2, FlipDir1, FlipDir2, DName1, DName2, GeometryPattern, VaryInstance)
            Feature? pattern;
            try
            {
                pattern = doc.FeatureManager.FeatureLinearPattern3(
                    d1Count,   // Num1
                    d1Spacing, // Spacing1
                    d2Count,   // Num2
                    d2Spacing, // Spacing2
                    false,     // FlipDir1
                    false,     // FlipDir2
                    "D1",      // DName1
                    "D2",      // DName2
                    false,     // GeometryPattern
                    false);    // VaryInstance
            }
            catch
            {
                return "ERROR: Linear pattern failed — contact support";
            }

            if (pattern == null) return "ERROR: Linear pattern failed";

            RegisterFeature(op.Id, pattern);
            return $"Linear pattern {d1Count}×{d2Count}";
        }

        // ── mirror ────────────────────────────────────────────────────────────

        private string ExecMirror(IModelDoc2 doc, OperationDto op)
        {
            if (op.SourceIds == null || op.SourceIds.Length == 0)
                return "ERROR: mirror requires source_ids";

            string mirrorPlane = op.MirrorPlane ?? "Right Plane";
            doc.ClearSelection2(true);

            // Select mirror plane with mark=1.
            doc.Extension.SelectByID2(mirrorPlane, "PLANE", 0, 0, 0, false, 1, null, 0);

            // Select source features with mark=4.
            foreach (string sid in op.SourceIds)
            {
                if (_features.TryGetValue(sid, out Feature src))
                    src.Select2(true, 4);
            }

            // InsertMirrorFeature2(BMirrorBody, BGeometryPattern, BMerge, BKnit, ScopeOptions)
            Feature? mirror = doc.FeatureManager.InsertMirrorFeature2(false, false, true, false, 0);
            if (mirror == null) return "ERROR: Mirror failed";

            RegisterFeature(op.Id, mirror);
            return $"Mirror about {mirrorPlane}";
        }

        // ── revolve ───────────────────────────────────────────────────────────

        private string ExecRevolve(IModelDoc2 doc, OperationDto op)
        {
            if (string.IsNullOrEmpty(op.ProfileId))
                return "ERROR: revolve requires profile_id";

            SelectRegisteredFeature(doc, op.ProfileId!);

            double angle = (op.AngleDeg ?? 360.0) * Math.PI / 180.0;

            // FeatureRevolve2: SingleDir,IsSolid,IsThin,IsCut,ReverseDir,BothDirUpToSame,
            //   Dir1Type,Dir2Type,Dir1Angle,Dir2Angle,OffsetReverse1,OffsetReverse2,
            //   OffsetDistance1,OffsetDistance2,ThinType,ThinThickness1,ThinThickness2,
            //   Merge,UseFeatScope,UseAutoSelect
            Feature? feature = doc.FeatureManager.FeatureRevolve2(
                true,  // SingleDir
                true,  // IsSolid
                false, // IsThin
                false, // IsCut
                false, // ReverseDir
                false, // BothDirectionUpToSameEntity
                (int)swEndConditions_e.swEndCondBlind,
                (int)swEndConditions_e.swEndCondBlind,
                angle, // Dir1Angle
                0.0,   // Dir2Angle
                false, // OffsetReverse1
                false, // OffsetReverse2
                0.0,   // OffsetDistance1
                0.0,   // OffsetDistance2
                0,     // ThinType
                0.0,   // ThinThickness1
                0.0,   // ThinThickness2
                true,  // Merge
                false, // UseFeatScope
                true); // UseAutoSelect

            if (feature == null) return "ERROR: Revolve failed — sketch must have a centerline";

            RegisterFeature(op.Id, feature);
            doc.ForceRebuild3(false);
            return $"Revolve {op.AngleDeg ?? 360.0:0.#}°";
        }

        // ── delete_feature ────────────────────────────────────────────────────

        private string ExecDeleteFeature(IModelDoc2 doc, OperationDto op)
        {
            var toDelete = new List<Feature>();

            if (op.FeatureIds != null && op.FeatureIds.Length > 0)
            {
                // Delete by registered op ID or by SolidWorks feature name.
                var nameSet = new HashSet<string>(op.FeatureIds, StringComparer.OrdinalIgnoreCase);
                Feature f = (Feature)doc.FirstFeature();
                while (f != null)
                {
                    if (nameSet.Contains(f.Name ?? "") ||
                        op.FeatureIds.Any(id => _features.TryGetValue(id, out Feature reg) && reg == f))
                        toDelete.Add(f);
                    f = (Feature)f.GetNextFeature();
                }
            }
            else if (op.LastN.HasValue)
            {
                int n = Math.Max(1, op.LastN.Value);
                var all = CollectUserFeatures(doc);
                int start = Math.Max(0, all.Count - n);
                toDelete.AddRange(all.GetRange(start, all.Count - start));
            }
            else
            {
                // Delete all user features.
                toDelete.AddRange(CollectUserFeatures(doc));
            }

            if (toDelete.Count == 0) return "No deletable features found.";

            doc.ClearSelection2(true);
            foreach (Feature item in toDelete)
                item.Select2(true, 0);

            int opts = (int)swDeleteSelectionOptions_e.swDelete_Absorbed |
                       (int)swDeleteSelectionOptions_e.swDelete_Children;
            doc.Extension.DeleteSelection2(opts);
            doc.ForceRebuild3(false);

            string noun = toDelete.Count == 1 ? "feature" : "features";
            return $"Deleted {toDelete.Count} {noun}";
        }

        // ── update_title_block ────────────────────────────────────────────────

        private string ExecUpdateTitleBlock(IModelDoc2 doc, OperationDto op)
        {
            if (op.TitleBlock == null) return "ERROR: title_block fields required";

            var customProps = (CustomPropertyManager)doc.Extension.get_CustomPropertyManager("");

            var fields = new Dictionary<string, string>();
            if (!string.IsNullOrEmpty(op.TitleBlock.Revision))   fields["Revision"]    = op.TitleBlock.Revision!;
            if (!string.IsNullOrEmpty(op.TitleBlock.DrawnBy))    fields["DrawnBy"]     = op.TitleBlock.DrawnBy!;
            if (!string.IsNullOrEmpty(op.TitleBlock.CheckedBy))  fields["CheckedBy"]   = op.TitleBlock.CheckedBy!;
            if (!string.IsNullOrEmpty(op.TitleBlock.Title))      fields["Description"] = op.TitleBlock.Title!;
            if (!string.IsNullOrEmpty(op.TitleBlock.Description)) fields["Description"] = op.TitleBlock.Description!;
            if (!string.IsNullOrEmpty(op.TitleBlock.Date))       fields["Date"]        = op.TitleBlock.Date!;
            foreach (var kv in op.TitleBlock.Custom ?? new Dictionary<string, string>())
                fields[kv.Key] = kv.Value;

            var updated = new List<string>();
            foreach (var kv in fields)
            {
                // Add3 with swCustomPropertyReplaceValue(2) creates or updates the property.
                customProps.Add3(kv.Key, (int)swCustomInfoType_e.swCustomInfoText, kv.Value,
                    (int)swCustomPropertyAddOption_e.swCustomPropertyReplaceValue);
                updated.Add($"{kv.Key}={kv.Value}");
            }

            if (updated.Count == 0) return "NOOP: no title block fields provided";
            return $"Title block updated: {string.Join(", ", updated)}";
        }

        // ── export_file ───────────────────────────────────────────────────────

        private string ExecExportFile(IModelDoc2 doc, OperationDto op)
        {
            if (op.ExportFile == null) return "ERROR: export_file config required";

            string docPath = doc.GetPathName() ?? "";
            if (string.IsNullOrEmpty(docPath) && string.IsNullOrEmpty(op.ExportFile.OutputPath))
                return "ERROR: export_file requires the document to be saved first (File → Save), or specify output_path";

            string dir     = op.ExportFile.OutputPath ?? Path.GetDirectoryName(docPath) ?? "";
            if (string.IsNullOrEmpty(dir)) dir = Path.GetTempPath();
            if (!Directory.Exists(dir))
                return $"ERROR: export output directory does not exist: {dir}";

            string baseName = BuildExportFilename(doc, op.ExportFile.FilenameTemplate
                               ?? Path.GetFileNameWithoutExtension(docPath));

            string ext = (op.ExportFile.Format ?? "PDF").ToUpper() switch {
                "PDF"  => ".pdf",
                "DXF"  => ".dxf",
                "STEP" => ".step",
                "IGES" => ".igs",
                "STL"  => ".stl",
                _      => ".pdf"
            };

            string outPath = Path.Combine(dir, baseName + ext);

            int errors = 0, warnings = 0;
            bool ok = doc.Extension.SaveAs3(outPath,
                (int)swSaveAsVersion_e.swSaveAsCurrentVersion,
                (int)swSaveAsOptions_e.swSaveAsOptions_Silent,
                null, null, ref errors, ref warnings);

            if (!ok) return $"ERROR: Export failed (errors={errors} warnings={warnings})";
            return $"Exported to {outPath}";
        }

        private string BuildExportFilename(IModelDoc2 doc, string template)
        {
            var cpm = (CustomPropertyManager)doc.Extension.get_CustomPropertyManager("");
            string Get(string key) {
                string val = "", res = "";
                bool wasResolved;
                cpm.Get5(key, false, out val, out res, out wasResolved);
                return string.IsNullOrEmpty(res) ? val : res;
            }
            return template
                .Replace("{title}",    Get("Description").Replace(" ", "_"))
                .Replace("{revision}", Get("Revision"))
                .Replace("{date}",     DateTime.Now.ToString("yyyy-MM-dd"))
                .Replace("{docname}",  Path.GetFileNameWithoutExtension(doc.GetPathName() ?? "part"));
        }

        // ── check_drawing ─────────────────────────────────────────────────────

        private string ExecCheckDrawing(IModelDoc2 doc, OperationDto op)
        {
            DrawingDoc? drawing = doc as DrawingDoc;
            if (drawing == null) return "ERROR: check_drawing requires an active drawing document";

            var issues = new List<string>();

            // Check 1: required title block custom properties present
            var cpm = (CustomPropertyManager)doc.Extension.get_CustomPropertyManager("");
            string[] required = { "Description", "Revision", "DrawnBy" };
            foreach (string key in required)
            {
                string val = "", res = "";
                bool wasResolved;
                cpm.Get5(key, false, out val, out res, out wasResolved);
                if (string.IsNullOrWhiteSpace(val) && string.IsNullOrWhiteSpace(res))
                    issues.Add($"MISSING_PROPERTY: '{key}' is empty");
            }

            // Check 2: sheets have views — restore active sheet afterwards
            string? originalSheet = (drawing.GetCurrentSheet() as ISheet)?.GetName();
            object[]? sheets = drawing.GetSheetNames() as object[];
            foreach (object sheetName in sheets ?? Array.Empty<object>())
            {
                drawing.ActivateSheet(sheetName.ToString()!);
                object[]? views = drawing.GetViews() as object[];
                if (views == null || views.Length == 0)
                    issues.Add($"EMPTY_SHEET: sheet '{sheetName}' has no drawing views");
            }
            if (originalSheet != null) drawing.ActivateSheet(originalSheet);

            // Check 3: dangling dimensions
            object[]? annots = doc.Extension.GetAnnotations() as object[];
            int danglingCount = 0;
            if (annots != null)
            {
                foreach (object annotObj in annots)
                {
                    Annotation? ann = annotObj as Annotation;
                    if (ann == null) continue;
                    if (ann.IsDangling()) danglingCount++;
                }
            }
            if (danglingCount > 0)
                issues.Add($"DANGLING_DIMENSIONS: {danglingCount} dimension(s) not attached to geometry");

            if (issues.Count == 0) return "Drawing check PASSED: no issues found";
            return "Drawing check ISSUES:\n" + string.Join("\n", issues.Select(i => "  • " + i));
        }

        // ── helpers ───────────────────────────────────────────────────────────

        private IModelDoc2? EnsurePartDoc(bool createIfMissing)
        {
            IModelDoc2? doc = (IModelDoc2)_swApp.ActiveDoc;
            if (doc == null && createIfMissing)
            {
                _swApp.NewPart();
                doc = (IModelDoc2)_swApp.ActiveDoc;
            }
            if (doc == null) return null;
            if (doc.GetType() != (int)swDocumentTypes_e.swDocPART) return null;
            return doc;
        }

        /// <summary>
        /// Selects a named standard plane, or "<feature_id> top/bottom" using
        /// the bounding-box face-selection pattern.
        /// </summary>
        private bool SelectPlaneOrFace(IModelDoc2 doc, string plane)
        {
            if (IsStandardPlaneName(plane))
            {
                doc.ClearSelection2(true);
                return doc.Extension.SelectByID2(plane, "PLANE", 0, 0, 0, false, 0, null, 0);
            }

            if (plane.StartsWith("top_face_of:", StringComparison.OrdinalIgnoreCase))
            {
                string featureName = plane.Substring("top_face_of:".Length).Trim();
                if (_features.TryGetValue(featureName, out Feature namedFeature))
                    return SelectFaceOfFeature(doc, namedFeature, topFace: true);
                Feature? docFeature = FindFeatureByName(doc, featureName);
                if (docFeature != null)
                    return SelectFaceOfFeature(doc, docFeature, topFace: true);
                return SelectTopFaceOfBody(doc);
            }

            if (string.Equals(plane, "active_top_face", StringComparison.OrdinalIgnoreCase))
                return SelectTopFaceOfBody(doc);

            // "<feature_id> top" or "<feature_id> bottom"
            string lower = plane.ToLowerInvariant();
            bool wantTop = !lower.Contains("bottom");
            string featureId = plane.Split(' ')[0];

            if (_features.TryGetValue(featureId, out Feature feat))
                return SelectFaceOfFeature(doc, feat, wantTop);

            Feature? fallbackFeature = FindFeatureByName(doc, featureId);
            if (fallbackFeature != null && SelectFaceOfFeature(doc, fallbackFeature, wantTop))
                return true;

            return wantTop ? SelectTopFaceOfBody(doc) : SelectBottomFaceOfBody(doc);
        }

        private bool SelectHoleSketchReference(IModelDoc2 doc, string faceOf)
        {
            if (IsStandardPlaneName(faceOf))
            {
                doc.ClearSelection2(true);
                return doc.Extension.SelectByID2(faceOf, "PLANE", 0, 0, 0, false, 0, null, 0);
            }

            if (string.Equals(faceOf, "active_top_face", StringComparison.OrdinalIgnoreCase))
                return SelectTopFaceOfBody(doc);

            if (_features.TryGetValue(faceOf, out Feature registeredFeat) &&
                SelectFaceOfFeature(doc, registeredFeat, topFace: true))
            {
                return true;
            }

            // Feature references can be stale or absent in follow-up requests. Fall back to
            // actual solid geometry and select the highest horizontal planar face.
            return SelectTopFaceOfBody(doc);
        }

        private static bool IsStandardPlaneName(string plane)
        {
            return plane == "Top Plane" || plane == "Front Plane" || plane == "Right Plane";
        }

        /// <summary>
        /// Selects the top or bottom horizontal planar face exposed by a feature.
        /// </summary>
        private static bool SelectFaceOfFeature(IModelDoc2 doc, Feature feature, bool topFace)
        {
            object[]? faceArr;
            try
            {
                faceArr = feature.GetFaces() as object[];
            }
            catch
            {
                return false;
            }

            return SelectPlanarFaceByZ(doc, FaceObjects(faceArr), topFace);
        }

        /// <summary>
        /// Selects the topmost horizontal planar face across all solid bodies in the document.
        /// Used as a fallback when the LLM references a feature not in the current registry.
        /// </summary>
        private static bool SelectTopFaceOfBody(IModelDoc2 doc)
        {
            return SelectPlanarFaceByZ(doc, CollectSolidBodyFaces(doc), topFace: true);
        }

        private static bool SelectBottomFaceOfBody(IModelDoc2 doc)
        {
            return SelectPlanarFaceByZ(doc, CollectSolidBodyFaces(doc), topFace: false);
        }

        private static bool SelectPlanarFaceByZ(IModelDoc2 doc, IEnumerable<Face2> faces, bool topFace)
        {
            Face2? chosen = FindPlanarFaceByZ(faces, topFace);
            if (chosen == null) return false;
            return SelectFace(doc, chosen);
        }

        private static Face2? FindPlanarFaceByZ(IEnumerable<Face2> faces, bool topFace)
        {
            Face2? chosen = null;
            double extremeZ = topFace ? double.MinValue : double.MaxValue;
            double chosenArea = double.MinValue;

            foreach (Face2 face in faces)
            {
                double[]? box = GetFaceBox(face);
                if (box == null || !IsHorizontalPlanarFace(face, box))
                    continue;

                double faceZ = topFace ? box[5] : box[2];
                double area = GetFaceArea(face);
                bool betterZ = topFace
                    ? faceZ > extremeZ + 1e-7
                    : faceZ < extremeZ - 1e-7;
                bool sameZLargerFace = Math.Abs(faceZ - extremeZ) <= 1e-7 && area > chosenArea;

                if (chosen == null || betterZ || sameZLargerFace)
                {
                    extremeZ = faceZ;
                    chosen = face;
                    chosenArea = area;
                }
            }

            return chosen;
        }

        private static IEnumerable<Face2> FaceObjects(object[]? faceArr)
        {
            if (faceArr == null) yield break;

            foreach (object faceObj in faceArr)
            {
                if (faceObj is Face2 face)
                    yield return face;
            }
        }

        private static IEnumerable<Face2> CollectSolidBodyFaces(IModelDoc2 doc)
        {
            IPartDoc? part = doc as IPartDoc;
            object[]? bodies = part?.GetBodies2((int)swBodyType_e.swSolidBody, true) as object[];
            if (bodies == null) yield break;

            foreach (object bodyObj in bodies)
            {
                if (!(bodyObj is IBody2 body)) continue;

                object[]? faces = body.GetFaces() as object[];
                foreach (Face2 face in FaceObjects(faces))
                    yield return face;
            }
        }

        private static bool SelectFace(IModelDoc2 doc, Face2 face)
        {
            try
            {
                doc.ClearSelection2(true);
                return ((IEntity)face).Select4(false, null);
            }
            catch
            {
                return false;
            }
        }

        private static bool IsHorizontalPlanarFace(Face2 face, double[] box)
        {
            if (!IsPlanarFace(face))
                return false;

            if (Math.Abs(box[5] - box[2]) <= 1e-5)
                return true;

            double[]? normal = GetFaceNormal(face);
            return normal != null && normal.Length >= 3 && Math.Abs(normal[2]) >= 0.707;
        }

        private static bool IsPlanarFace(Face2 face)
        {
            try
            {
                Surface? surface = face.GetSurface() as Surface;
                if (surface != null)
                    return surface.IsPlane();
            }
            catch
            {
            }

            try
            {
                Surface? surface = face.IGetSurface();
                return surface != null && surface.IsPlane();
            }
            catch
            {
                return false;
            }
        }

        private static double[]? GetFaceBox(Face2 face)
        {
            try
            {
                double[]? box = ToDoubleArray(face.GetBox());
                return box != null && box.Length >= 6 ? box : null;
            }
            catch
            {
                return null;
            }
        }

        private static double[]? GetFaceNormal(Face2 face)
        {
            try
            {
                return ToDoubleArray(face.Normal);
            }
            catch
            {
                return null;
            }
        }

        private static double GetFaceArea(Face2 face)
        {
            try
            {
                return face.GetArea();
            }
            catch
            {
                return 0.0;
            }
        }

        private void SelectRegisteredFeature(IModelDoc2 doc, string opId)
        {
            if (!_features.TryGetValue(opId, out Feature feat)) return;
            doc.ClearSelection2(true);
            feat.Select2(false, 0);
        }

        private bool IsActiveSketch(string? sketchId)
        {
            return _activeSketchId != null &&
                   string.Equals(_activeSketchId, sketchId, StringComparison.OrdinalIgnoreCase);
        }

        private string CloseActiveSketch(IModelDoc2 doc, string sketchId)
        {
            try
            {
                doc.SketchManager.InsertSketch(true);
                Feature? sketchFeat = FindLastFeatureOfType(doc, "ProfileFeature", "3DProfileFeature");
                if (sketchFeat != null)
                {
                    try { sketchFeat.Name = sketchId; } catch { }
                    RegisterFeature(sketchId, sketchFeat);
                }
                _activeSketchId = null;
                return $"Closed sketch '{sketchId}'";
            }
            catch (Exception ex)
            {
                return "ERROR: Could not close active sketch: " + ex.Message;
            }
        }

        private void RegisterFeature(string? opId, Feature feature)
        {
            string opKey = opId?.Trim() ?? string.Empty;
            if (opKey.Length > 0)
                _features[opKey] = feature;

            try
            {
                string featureName = feature.Name;
                if (!string.IsNullOrWhiteSpace(featureName))
                    _features[featureName] = feature;
            }
            catch { }

            _lastCreatedFeatures.Add(feature);
        }

        /// <summary>
        /// Selects all edges of the specified features (empty list = all user features).
        /// Returns true if at least one edge was selected.
        /// </summary>
        private bool SelectEdgesForFillet(IModelDoc2 doc, string[] featureIds)
        {
            doc.ClearSelection2(true);
            bool anySelected = false;

            if (featureIds != null &&
                featureIds.Any(id =>
                    string.Equals(id, "__top_edges__", StringComparison.OrdinalIgnoreCase) ||
                    string.Equals(id, "top_edges", StringComparison.OrdinalIgnoreCase)))
            {
                return SelectTopFaceBoundaryEdges(doc);
            }

            if (featureIds == null || featureIds.Length == 0)
            {
                // "all edges" — IBody2.GetEdges() returns each edge exactly once;
                // no deduplication needed when walking body edges directly.
                IPartDoc? part = doc as IPartDoc;
                object[]? bodies = part?.GetBodies2(
                    (int)swBodyType_e.swSolidBody, true) as object[];
                if (bodies == null) return false;
                foreach (object bodyObj in bodies)
                {
                    IBody2? body = bodyObj as IBody2;
                    if (body == null) continue;
                    object[]? edges = body.GetEdges() as object[];
                    if (edges == null) continue;
                    foreach (object edgeObj in edges)
                    {
                        try {
                            ((IEntity)edgeObj).Select4(anySelected, null);
                            anySelected = true;
                        } catch { }
                    }
                }
            }
            else
            {
                // Named features: use body-based edge walk for the bodies those features belong to.
                // Face-based walks produce duplicate edges (each edge borders two faces).
                IPartDoc? part = doc as IPartDoc;
                object[]? bodies = part?.GetBodies2((int)swBodyType_e.swSolidBody, true) as object[];
                if (bodies != null)
                {
                    foreach (object bodyObj in bodies)
                    {
                        IBody2? body = bodyObj as IBody2;
                        if (body == null) continue;
                        object[]? edges = body.GetEdges() as object[];
                        if (edges == null) continue;
                        foreach (object edgeObj in edges)
                        {
                            try {
                                ((IEntity)edgeObj).Select4(anySelected, null);
                                anySelected = true;
                            } catch { }
                        }
                    }
                }
            }
            return anySelected;
        }

        private static bool SelectTopFaceBoundaryEdges(IModelDoc2 doc)
        {
            Face2? topFace = FindPlanarFaceByZ(CollectSolidBodyFaces(doc), topFace: true);
            if (topFace == null) return false;

            object[]? edges;
            try
            {
                edges = topFace.GetEdges() as object[];
            }
            catch
            {
                return false;
            }

            if (edges == null || edges.Length == 0) return false;

            doc.ClearSelection2(true);
            bool anySelected = false;
            foreach (object edgeObj in edges)
            {
                try
                {
                    ((IEntity)edgeObj).Select4(anySelected, null);
                    anySelected = true;
                }
                catch { }
            }

            return anySelected;
        }

        private static List<Feature> CollectUserFeatures(IModelDoc2 doc)
        {
            var result = new List<Feature>();
            Feature f = (Feature)doc.FirstFeature();
            while (f != null)
            {
                if (!_systemTypes.Contains(f.GetTypeName2() ?? ""))
                    result.Add(f);
                f = (Feature)f.GetNextFeature();
            }
            return result;
        }

        private static Feature? FindLastFeatureOfType(IModelDoc2 doc, params string[] typeNames)
        {
            var types = new HashSet<string>(typeNames);
            Feature? last = null;
            Feature f = (Feature)doc.FirstFeature();
            while (f != null)
            {
                if (types.Contains(f.GetTypeName2() ?? "")) last = f;
                f = (Feature)f.GetNextFeature();
            }
            return last;
        }

        private static Feature? FindFeatureByName(IModelDoc2 doc, string name)
        {
            Feature? f = (Feature?)doc.FirstFeature();
            while (f != null)
            {
                if (string.Equals(f.Name ?? "", name, StringComparison.OrdinalIgnoreCase))
                    return f;
                f = (Feature?)f.GetNextFeature();
            }
            return null;
        }

        /// <summary>Converts nullable mm value to metres. Null → 0.</summary>
        /// <summary>Extracts a compact JSON report of the current part after execution.</summary>
        public static string ExtractPartReport(IModelDoc2 doc)
        {
            try
            {
                IPartDoc? part = doc as IPartDoc;
                object[] bodies = part?.GetBodies2((int)swBodyType_e.swSolidBody, true) as object[]
                                  ?? System.Array.Empty<object>();

                double[]? box = GetCombinedBodyBox(bodies);
                var features = CollectFeatureReports(doc);
                var bbox = box == null
                    ? null
                    : new
                    {
                        x_mm = Math.Round((box[3] - box[0]) * 1000.0, 3),
                        y_mm = Math.Round((box[4] - box[1]) * 1000.0, 3),
                        z_mm = Math.Round((box[5] - box[2]) * 1000.0, 3),
                    };

                var report = new
                {
                    document_type = "part",
                    rebuild_status = "success",
                    body_count = bodies.Length,
                    bounding_box = bbox,
                    bounding_box_mm = bbox,
                    mass_g = Math.Round(EstimateMassGrams(doc, bodies), 3),
                    feature_count = features.Count,
                    features,
                    sketches = CollectSketchReports(doc),
                };

                return JsonConvert.SerializeObject(report, Formatting.None);
            }
            catch (Exception ex)
            {
                var errorReport = new
                {
                    error = "part_report_failed",
                    message = ex.Message,
                };
                return JsonConvert.SerializeObject(errorReport, Formatting.None);
            }
        }

        private static double[]? GetCombinedBodyBox(object[] bodies)
        {
            double[]? combined = null;

            foreach (object bodyObj in bodies)
            {
                if (!(bodyObj is IBody2 body)) continue;
                double[]? bodyBox = ToDoubleArray(body.GetBodyBox());
                if (bodyBox == null || bodyBox.Length < 6) continue;

                if (combined == null)
                {
                    combined = new[] { bodyBox[0], bodyBox[1], bodyBox[2], bodyBox[3], bodyBox[4], bodyBox[5] };
                }
                else
                {
                    combined[0] = Math.Min(combined[0], bodyBox[0]);
                    combined[1] = Math.Min(combined[1], bodyBox[1]);
                    combined[2] = Math.Min(combined[2], bodyBox[2]);
                    combined[3] = Math.Max(combined[3], bodyBox[3]);
                    combined[4] = Math.Max(combined[4], bodyBox[4]);
                    combined[5] = Math.Max(combined[5], bodyBox[5]);
                }
            }

            return combined;
        }

        private static double EstimateMassGrams(IModelDoc2 doc, object[] bodies)
        {
            double[]? massProps = ToDoubleArray(doc.GetMassProperties());
            double volumeM3 = 0.0;

            if (massProps != null && massProps.Length > 0 && massProps[0] > 0)
            {
                volumeM3 = massProps[0];
            }
            else
            {
                foreach (object bodyObj in bodies)
                {
                    if (!(bodyObj is IBody2 body)) continue;
                    double[]? bodyMassProps = ToDoubleArray(body.GetMassProperties(7800.0));
                    if (bodyMassProps != null && bodyMassProps.Length > 0 && bodyMassProps[0] > 0)
                        volumeM3 += bodyMassProps[0];
                }
            }

            const double steelDensityKgPerM3 = 7800.0;
            return volumeM3 * steelDensityKgPerM3 * 1000.0;
        }

        private static List<object> CollectFeatureReports(IModelDoc2 doc)
        {
            var features = new List<object>();
            Feature? f = (Feature?)doc.FirstFeature();
            while (f != null)
            {
                features.Add(new
                {
                    name = f.Name ?? string.Empty,
                    type = f.GetTypeName2() ?? string.Empty,
                    suppressed = IsFeatureSuppressed(f),
                });

                f = (Feature?)f.GetNextFeature();
            }

            return features;
        }

        private static List<object> CollectSketchReports(IModelDoc2 doc)
        {
            var sketches = new List<object>();
            Feature? f = (Feature?)doc.FirstFeature();
            while (f != null)
            {
                string type = f.GetTypeName2() ?? string.Empty;
                if (type == "ProfileFeature" || type == "3DProfileFeature")
                {
                    sketches.Add(new
                    {
                        name = f.Name ?? string.Empty,
                        entity_count = CountSketchEntities(f),
                        dimension_count = CountSketchDisplayDimensions(f),
                    });
                }
                f = (Feature?)f.GetNextFeature();
            }

            return sketches;
        }

        private static int CountSketchEntities(Feature feature)
        {
            try
            {
                Sketch? sketch = feature.GetSpecificFeature2() as Sketch;
                object[]? segments = sketch?.GetSketchSegments() as object[];
                return segments?.Length ?? -1;
            }
            catch
            {
                return -1;
            }
        }

        private static int CountSketchDisplayDimensions(Feature feature)
        {
            try
            {
                int count = 0;
                object? dim = feature.GetFirstDisplayDimension();
                while (dim != null)
                {
                    count++;
                    dim = feature.GetNextDisplayDimension(dim);
                }
                return count;
            }
            catch
            {
                return -1;
            }
        }

        public static string ExtractPartCorpus(string folderPath, string? outputPath = null)
        {
            // This would be the implementation for extracting SolidWorks feature corpus
            // For now, returning a placeholder
            return "Corpus extraction not yet implemented";
        }

        private static bool IsFeatureSuppressed(Feature feature)
        {
            try
            {
                return feature.IsSuppressed();
            }
            catch
            {
                return false;
            }
        }


        private static double[]? ToDoubleArray(object? value)
        {
            if (value is double[] doubles)
                return doubles;

            if (value is object[] objects)
            {
                var result = new double[objects.Length];
                for (int i = 0; i < objects.Length; i++)
                    result[i] = Convert.ToDouble(objects[i]);
                return result;
            }

            return null;
        }

        private static double Mm(double? value) => (value ?? 0.0) / 1000.0;

        /// <summary>Returns the standard clearance hole diameter for a given fastener.</summary>
        private static double HoleDiameterMm(string fastenerSize, string holeType)
        {
            if (string.Equals(holeType, "counterbore", StringComparison.OrdinalIgnoreCase))
                return CounterboreDiameterMm(fastenerSize);

            return ClearanceHoleDiameterMm(fastenerSize);
        }

        private static double ClearanceHoleDiameterMm(string fastenerSize)
        {
            // Metric clearance hole diameters (ISO 273 medium fit)
            switch (fastenerSize.ToUpperInvariant())
            {
                case "M3":  return 3.4;
                case "M4":  return 4.5;
                case "M5":  return 5.5;
                case "M6":  return 6.6;
                case "M8":  return 9.0;
                case "M10": return 11.0;
                case "M12": return 13.5;
                default:    return 6.6; // M6 fallback
            }
        }

        private static double CounterboreDiameterMm(string fastenerSize)
        {
            // Socket head cap screw counterbores (ISO 4762)
            switch (fastenerSize.ToUpperInvariant())
            {
                case "M3":  return 6.5;
                case "M4":  return 8.0;
                case "M5":  return 9.5;
                case "M6":  return 11.0;
                case "M8":  return 14.0;
                case "M10": return 17.5;
                case "M12": return 20.0;
                default:    return 11.0; // M6 fallback
            }
        }

        private static double CounterboreDepthMm(string fastenerSize)
        {
            // Socket head cap screw head heights (ISO 4762)
            switch (fastenerSize.ToUpperInvariant())
            {
                case "M3":  return 3.0;
                case "M4":  return 4.0;
                case "M5":  return 5.0;
                case "M6":  return 6.0;
                case "M8":  return 8.0;
                case "M10": return 10.0;
                case "M12": return 12.0;
                default:    return 6.0; // M6 fallback
            }
        }
    }
}

