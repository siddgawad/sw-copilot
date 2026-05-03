using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
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

        private static readonly HashSet<string> _systemTypes = new HashSet<string>
        {
            "RefPlane", "OriginProfileFeature", "Reference", "HistoryFolder",
            "SelectionSetFolder", "SensorFolder", "MaterialFolder",
            "CommentsFolder", "DesignBinder",
        };

        public OperationExecutor(ISldWorks swApp)
        {
            _swApp = swApp;
        }

        public string Execute(OperationGraphDto graph)
        {
            IModelDoc2? doc = EnsurePartDoc(createIfMissing: true);
            if (doc == null) return "ERROR: No active part document.";

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
                return $"RULE VIOLATION — execution refused:\n{ruleViolation}";

            bool anyError = false;
            foreach (OperationDto op in graph.Operations ?? System.Array.Empty<OperationDto>())
            {
                string result;
                try
                {
                    result = Dispatch(doc, op);
                }
                catch (Exception ex)
                {
                    result = "ERROR: " + ex.Message;
                }

                lines.Add($"[{op.Id}] {result}");

                if (result.StartsWith("ERROR", StringComparison.OrdinalIgnoreCase))
                {
                    anyError = true;
                    break;
                }
            }

            if (!anyError)
                doc.ForceRebuild3(false);

            return string.Join("\n", lines);
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
                        // Sanity-check: clearance hole radius must not exceed any plausible part face.
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

        // ── Dispatcher ────────────────────────────────────────────────────────

        private string Dispatch(IModelDoc2 doc, OperationDto op)
        {
            switch ((op.Type ?? "").Trim().ToLowerInvariant())
            {
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
                case "noop":              return op.Message ?? "No operation.";
                default:                  return $"Unknown operation type: {op.Type}";
            }
        }

        // ── sketch ────────────────────────────────────────────────────────────

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

            skMgr.InsertSketch(true); // close sketch

            // Register the last sketch feature so later ops can reference this op id.
            Feature? sketchFeat = FindLastFeatureOfType(doc, "ProfileFeature", "3DProfileFeature");
            if (sketchFeat != null)
                _features[op.Id] = sketchFeat;

            return $"Sketch on {plane} with {drawn} entities";
        }

        // ── extrude_boss ──────────────────────────────────────────────────────

        private string ExecExtrudeBoss(IModelDoc2 doc, OperationDto op)
        {
            if (string.IsNullOrEmpty(op.ProfileId))
                return "ERROR: extrude_boss requires profile_id";

            double depth = Mm(op.DepthMm);
            if (depth <= 0) return "ERROR: extrude_boss depth_mm must be positive";

            SelectRegisteredFeature(doc, op.ProfileId!);

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

            if (!string.IsNullOrWhiteSpace(op.Name))
                try { feature.Name = op.Name; } catch { }

            _features[op.Id] = feature;
            doc.ForceRebuild3(false);
            return $"Extrude Boss {op.DepthMm:0.#} mm";
        }

        // ── extrude_cut ───────────────────────────────────────────────────────

        private string ExecExtrudeCut(IModelDoc2 doc, OperationDto op)
        {
            if (string.IsNullOrEmpty(op.ProfileId))
                return "ERROR: extrude_cut requires profile_id";

            SelectRegisteredFeature(doc, op.ProfileId!);

            bool thruAll = op.ThroughAll || (op.DepthMm ?? 0) <= 0;
            double depth = Mm(op.DepthMm);
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

            if (!string.IsNullOrWhiteSpace(op.Name))
                try { feature.Name = op.Name; } catch { }

            _features[op.Id] = feature;
            doc.ForceRebuild3(false);
            return thruAll ? "Extrude Cut through all" : $"Extrude Cut {op.DepthMm:0.#} mm";
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

            if (fillet == null) return "ERROR: Fillet failed — edges may not support this radius";

            _features[op.Id] = fillet;
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

            _features[op.Id] = chamfer;
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

            double holeDiameterMm = HoleDiameterMm(op.FastenerSize ?? "M6", op.HoleType ?? "simple");
            double holeRadius = holeDiameterMm / 2.0 / 1000.0; // to metres

            // Resolve the sketch plane:
            //   1. Standard plane name → select it directly
            //   2. Known feature ID in registry → select top face
            //   3. Unknown → select top face of the tallest body in the model
            string faceOf = op.FaceOf!;
            bool planeReady;
            if (faceOf == "Top Plane" || faceOf == "Front Plane" || faceOf == "Right Plane")
            {
                doc.ClearSelection2(true);
                planeReady = doc.Extension.SelectByID2(faceOf, "PLANE", 0, 0, 0, false, 0, null, 0);
            }
            else if (_features.TryGetValue(faceOf, out Feature registeredFeat))
            {
                planeReady = SelectFaceOfFeature(doc, registeredFeat, topFace: true);
            }
            else
            {
                // Feature not in registry (e.g. follow-up request): use highest face on any body.
                planeReady = SelectTopFaceOfBody(doc);
            }

            if (!planeReady)
                return $"ERROR: Could not select sketch plane for holes (face_of='{faceOf}')";

            // Draw all hole circles in one sketch.
            SketchManager skMgr = doc.SketchManager;
            skMgr.InsertSketch(true);

            foreach (HolePositionDto pos in positions)
                skMgr.CreateCircleByRadius(pos.XMm / 1000.0, pos.YMm / 1000.0, 0, holeRadius);

            skMgr.InsertSketch(true);

            bool thruAll = op.ThroughAll || (op.DepthMm ?? 0) <= 0;
            double depth = Mm(op.DepthMm);
            int endCond = thruAll
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

            _features[op.Id] = cut;
            doc.ForceRebuild3(false);
            string label = op.HoleType == "simple" ? "drill" : op.HoleType ?? "drill";
            return $"{positions.Length}× {op.FastenerSize} {label} hole(s)";
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

            _features[op.Id] = pattern;
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

            _features[op.Id] = pattern;
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

            _features[op.Id] = mirror;
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

            _features[op.Id] = feature;
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
            if (plane == "Top Plane" || plane == "Front Plane" || plane == "Right Plane")
            {
                doc.ClearSelection2(true);
                return doc.Extension.SelectByID2(plane, "PLANE", 0, 0, 0, false, 0, null, 0);
            }

            // "<feature_id> top" or "<feature_id> bottom"
            string lower = plane.ToLowerInvariant();
            bool wantTop = !lower.Contains("bottom");
            string featureId = plane.Split(' ')[0];

            if (_features.TryGetValue(featureId, out Feature feat))
                return SelectFaceOfFeature(doc, feat, wantTop);

            return false;
        }

        /// <summary>
        /// Selects the top or bottom face of a feature using bounding-box midpoint.
        /// </summary>
        private static bool SelectFaceOfFeature(IModelDoc2 doc, Feature feature, bool topFace)
        {
            object[]? faceArr = feature.GetFaces() as object[];
            if (faceArr == null || faceArr.Length == 0) return false;

            Face2? chosen = null;
            double extreme = topFace ? double.MinValue : double.MaxValue;

            foreach (object o in faceArr)
            {
                if (!(o is Face2 face)) continue;
                double[]? box = face.GetBox() as double[];
                if (box == null || box.Length < 6) continue;
                double midZ = (box[2] + box[5]) / 2.0;
                if (topFace ? midZ > extreme : midZ < extreme)
                {
                    extreme = midZ;
                    chosen  = face;
                }
            }

            if (chosen == null) return false;
            doc.ClearSelection2(true);
            ((IEntity)chosen).Select4(false, null);
            return true;
        }

        private bool SelectTopFaceOfFeature(IModelDoc2 doc, string featureId)
        {
            if (_features.TryGetValue(featureId, out Feature feat))
                return SelectFaceOfFeature(doc, feat, topFace: true);
            return false;
        }

        /// <summary>
        /// Selects the topmost face (highest midZ) across all solid bodies in the document.
        /// Used as a fallback when the LLM references a feature not in the current registry.
        /// </summary>
        private static bool SelectTopFaceOfBody(IModelDoc2 doc)
        {
            IPartDoc? part = doc as IPartDoc;
            object[]? bodies = part?.GetBodies2((int)swBodyType_e.swSolidBody, true) as object[];
            if (bodies == null || bodies.Length == 0) return false;

            Face2? chosen = null;
            double highestZ = double.MinValue;

            foreach (object bodyObj in bodies)
            {
                if (!(bodyObj is IBody2 body)) continue;
                object[]? faces = body.GetFaces() as object[];
                if (faces == null) continue;

                foreach (object faceObj in faces)
                {
                    if (!(faceObj is Face2 face)) continue;
                    double[]? box = face.GetBox() as double[];
                    if (box == null || box.Length < 6) continue;
                    double midZ = (box[2] + box[5]) / 2.0;
                    if (midZ > highestZ)
                    {
                        highestZ = midZ;
                        chosen   = face;
                    }
                }
            }

            if (chosen == null) return false;
            doc.ClearSelection2(true);
            ((IEntity)chosen).Select4(false, null);
            return true;
        }

        private void SelectRegisteredFeature(IModelDoc2 doc, string opId)
        {
            if (!_features.TryGetValue(opId, out Feature feat)) return;
            doc.ClearSelection2(true);
            feat.Select2(false, 0);
        }

        /// <summary>
        /// Selects all edges of the specified features (empty list = all user features).
        /// Returns true if at least one edge was selected.
        /// </summary>
        private bool SelectEdgesForFillet(IModelDoc2 doc, string[] featureIds)
        {
            List<Feature> targets;
            if (featureIds == null || featureIds.Length == 0)
            {
                targets = CollectUserFeatures(doc)
                    .Where(f => { string t = f.GetTypeName2() ?? ""; return t == "Boss" || t == "Cut"; })
                    .ToList();

                if (targets.Count == 0)
                    targets = CollectUserFeatures(doc);
            }
            else
            {
                targets = new List<Feature>();
                foreach (string fid in featureIds)
                {
                    if (_features.TryGetValue(fid, out Feature feat))
                        targets.Add(feat);
                }
            }

            bool anySelected = false;
            foreach (Feature feat in targets)
            {
                object[]? faceArr = feat.GetFaces() as object[];
                if (faceArr == null) continue;

                foreach (object faceObj in faceArr)
                {
                    if (!(faceObj is Face2 face)) continue;
                    object[]? edgeArr = face.GetEdges() as object[];
                    if (edgeArr == null) continue;

                    foreach (object edgeObj in edgeArr)
                    {
                        try
                        {
                            ((IEntity)edgeObj).Select4(anySelected, null);
                            anySelected = true;
                        }
                        catch { }
                    }
                }
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

        /// <summary>Converts nullable mm value to metres. Null → 0.</summary>
        private static double Mm(double? value) => (value ?? 0.0) / 1000.0;

        /// <summary>Returns the standard clearance hole diameter for a given fastener.</summary>
        private static double HoleDiameterMm(string fastenerSize, string holeType)
        {
            // Metric clearance hole diameters (ISO 273 medium fit)
            switch (fastenerSize.ToUpperInvariant())
            {
                case "M3":  return holeType == "counterbore" ? 6.5  : 3.4;
                case "M4":  return holeType == "counterbore" ? 8.0  : 4.5;
                case "M5":  return holeType == "counterbore" ? 9.5  : 5.5;
                case "M6":  return holeType == "counterbore" ? 11.0 : 6.6;
                case "M8":  return holeType == "counterbore" ? 14.0 : 9.0;
                case "M10": return holeType == "counterbore" ? 17.5 : 11.0;
                case "M12": return holeType == "counterbore" ? 20.0 : 13.5;
                default:    return 6.6; // M6 fallback
            }
        }
    }
}
