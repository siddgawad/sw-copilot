using System;
using System.Collections.Generic;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;
using SwCopilotAddin.Client;

namespace SwCopilotAddin.Execution
{
    public sealed class CadCommandExecutor
    {
        private readonly ISldWorks _swApp;

        public CadCommandExecutor(ISldWorks swApp)
        {
            _swApp = swApp;
        }

        public string Execute(CadCommandDto command)
        {
            string action = (command.Action ?? string.Empty).Trim().ToLowerInvariant();
            switch (action)
            {
                case "create_shape":
                    return ExecuteCreateShape(command);
                case "extrude_selected":
                    return ExecuteExtrudeSelected(command);
                case "delete_all":
                    return ExecuteDeleteAll();
                case "delete_named":
                    return ExecuteDeleteNamed(command);
                case "delete_last_n":
                    return ExecuteDeleteLastN(command);
                case "noop":
                    return string.IsNullOrWhiteSpace(command.Message) ? "OK\nNo CAD operation requested." : "OK\n" + command.Message;
                default:
                    return "Unsupported CAD command action: " + (command.Action ?? "<null>");
            }
        }

        private string ExecuteCreateShape(CadCommandDto command)
        {
            if (!string.IsNullOrWhiteSpace(command.TargetFace))
            {
                return "Unsupported target face command. Deterministic execution currently supports Top Plane, Front Plane, and Right Plane.";
            }

            IModelDoc2? doc = EnsurePartDocument(createIfMissing: true);
            if (doc == null)
                return "No active part document.";

            if (command.ClearExisting)
                DeleteGeneratedFeatures(doc);

            string shape = (command.ShapeType ?? string.Empty).Trim().ToLowerInvariant();
            switch (shape)
            {
                case "box":
                    return CreateBox(doc, command);
                case "cylinder":
                    return CreateCylinder(doc, command);
                default:
                    return "Unsupported shape type: " + (command.ShapeType ?? "<null>");
            }
        }

        private string ExecuteExtrudeSelected(CadCommandDto command)
        {
            IModelDoc2? doc = EnsurePartDocument(createIfMissing: false);
            if (doc == null)
                return "No active part document.";

            double depth = RequirePositive(command.DimensionsMeters.Depth ?? command.DimensionsMeters.Height, "depth");

            TryCloseActiveSketch(doc);
            ISelectionMgr selMgr = doc.ISelectionManager;
            if (selMgr == null || selMgr.GetSelectedObjectCount2(-1) == 0)
            {
                Feature? sketch = SelectMostRecentSketch(doc);
                if (sketch == null)
                    return "No selected or existing sketch found to extrude.";
            }

            Feature feature = doc.FeatureManager.FeatureExtrusion2(
                true, false, false,
                (int)swEndConditions_e.swEndCondBlind, 0,
                depth, 0.0,
                false, false, false, false,
                0.0, 0.0,
                false, false, false, false,
                true, true, true,
                0, 0.0, false);

            if (feature == null)
                return "Extrude failed. Select a closed sketch/profile and try again.";

            doc.ForceRebuild3(false);
            return "OK\nExtruded selected or latest sketch " + ToMillimetres(depth) + " mm.";
        }

        private string ExecuteDeleteAll()
        {
            IModelDoc2? doc = EnsurePartDocument(createIfMissing: false);
            if (doc == null)
                return "No active document.";

            int deleted = DeleteGeneratedFeatures(doc);
            doc.ForceRebuild3(false);
            return "OK\nDeleted " + deleted + " sketches/features.";
        }

        private string CreateBox(IModelDoc2 doc, CadCommandDto command)
        {
            double length = RequirePositive(command.DimensionsMeters.Length, "length");
            double width = RequirePositive(command.DimensionsMeters.Width, "width");
            double height = RequirePositive(command.DimensionsMeters.Height ?? command.DimensionsMeters.Depth, "height");

            if (!SelectPlane(doc, command.TargetPlane))
                return "Could not select " + PlaneName(command.TargetPlane) + ".";

            SketchManager sketchMgr = doc.SketchManager;
            sketchMgr.InsertSketch(true);
            sketchMgr.CreateCornerRectangle(-length / 2.0, -width / 2.0, 0, length / 2.0, width / 2.0, 0);
            sketchMgr.InsertSketch(true);

            Feature feature = doc.FeatureManager.FeatureExtrusion2(
                true, false, false,
                (int)swEndConditions_e.swEndCondBlind, 0,
                height, 0.0,
                false, false, false, false,
                0.0, 0.0,
                false, false, false, false,
                true, true, true,
                0, 0.0, false);

            if (feature == null)
                return "Extrude failed.";

            doc.ForceRebuild3(false);
            return "OK\nCreated a " + ToMillimetres(length) + " mm x " + ToMillimetres(width) + " mm x " + ToMillimetres(height) + " mm box.";
        }

        private string CreateCylinder(IModelDoc2 doc, CadCommandDto command)
        {
            double? radiusValue = command.DimensionsMeters.Radius;
            if (!radiusValue.HasValue && command.DimensionsMeters.Diameter.HasValue)
                radiusValue = command.DimensionsMeters.Diameter.Value / 2.0;

            double radius = RequirePositive(radiusValue, "radius");
            double height = RequirePositive(command.DimensionsMeters.Height ?? command.DimensionsMeters.Depth, "height");

            if (!SelectPlane(doc, command.TargetPlane))
                return "Could not select " + PlaneName(command.TargetPlane) + ".";

            SketchManager sketchMgr = doc.SketchManager;
            sketchMgr.InsertSketch(true);
            sketchMgr.CreateCircleByRadius(0.0, 0.0, 0.0, radius);
            sketchMgr.InsertSketch(true);

            Feature feature = doc.FeatureManager.FeatureExtrusion2(
                true, false, false,
                (int)swEndConditions_e.swEndCondBlind, 0,
                height, 0.0,
                false, false, false, false,
                0.0, 0.0,
                false, false, false, false,
                true, true, true,
                0, 0.0, false);

            if (feature == null)
                return "Extrude failed.";

            doc.ForceRebuild3(false);
            return "OK\nCreated a " + ToMillimetres(radius * 2.0) + " mm diameter x " + ToMillimetres(height) + " mm cylinder.";
        }

        private IModelDoc2? EnsurePartDocument(bool createIfMissing)
        {
            IModelDoc2? doc = (IModelDoc2)_swApp.ActiveDoc;
            if (doc == null && createIfMissing)
            {
                _swApp.NewPart();
                doc = (IModelDoc2)_swApp.ActiveDoc;
            }

            if (doc == null || doc.GetType() != (int)swDocumentTypes_e.swDocPART)
                return null;

            return doc;
        }

        private static bool SelectPlane(IModelDoc2 doc, string? plane)
        {
            doc.ClearSelection2(true);
            return doc.Extension.SelectByID2(PlaneName(plane), "PLANE", 0, 0, 0, false, 0, null, 0);
        }

        private static string PlaneName(string? plane)
        {
            switch ((plane ?? string.Empty).Trim())
            {
                case "Front Plane":
                    return "Front Plane";
                case "Right Plane":
                    return "Right Plane";
                default:
                    return "Top Plane";
            }
        }

        private static double RequirePositive(double? value, string name)
        {
            if (!value.HasValue || value.Value <= 0)
                throw new InvalidOperationException("CAD command missing positive " + name + " in metres.");
            return value.Value;
        }

        private static string ToMillimetres(double metres)
        {
            return (metres * 1000.0).ToString("0.###");
        }

        private static void TryCloseActiveSketch(IModelDoc2 doc)
        {
            try
            {
                SketchManager sketchMgr = doc.SketchManager;
                if (sketchMgr != null && sketchMgr.ActiveSketch != null)
                    sketchMgr.InsertSketch(true);
            }
            catch
            {
            }
        }

        private static Feature? SelectMostRecentSketch(IModelDoc2 doc)
        {
            Feature? latestSketch = null;
            Feature feat = (Feature)doc.FirstFeature();
            while (feat != null)
            {
                string typeName = feat.GetTypeName2() ?? "";
                if (typeName == "ProfileFeature" || typeName == "3DProfileFeature")
                    latestSketch = feat;
                feat = (Feature)feat.GetNextFeature();
            }

            if (latestSketch != null)
            {
                doc.ClearSelection2(true);
                latestSketch.Select2(false, 0);
            }

            return latestSketch;
        }

        private string ExecuteDeleteNamed(CadCommandDto command)
        {
            IModelDoc2? doc = EnsurePartDocument(createIfMissing: false);
            if (doc == null)
                return "No active document.";

            string[]? names = command.TargetReference?.FeatureNames;
            if (names == null || names.Length == 0)
                return "delete_named requires target_reference.feature_names.";

            // Primary: exact name match (case-insensitive).
            var nameSet = new HashSet<string>(names, StringComparer.OrdinalIgnoreCase);
            var toDelete = new List<Feature>();

            Feature f = (Feature)doc.FirstFeature();
            while (f != null)
            {
                if (nameSet.Contains(f.Name ?? string.Empty))
                    toDelete.Add(f);
                f = (Feature)f.GetNextFeature();
            }

            // Fallback: parse "Boss-Extrude5" / "Cut-Extrude5" → 0-based position index,
            // then match by position among all boss/cut extrudes.
            if (toDelete.Count == 0)
            {
                var indexTargets = new HashSet<int>();
                foreach (string n in names)
                {
                    string upper = n.Trim().ToUpperInvariant();
                    int parsed;
                    if (upper.StartsWith("BOSS-EXTRUDE") &&
                        int.TryParse(upper.Substring(12), out parsed))
                        indexTargets.Add(parsed - 1);
                    else if (upper.StartsWith("CUT-EXTRUDE") &&
                             int.TryParse(upper.Substring(11), out parsed))
                        indexTargets.Add(parsed - 1);
                }

                var extrudes = new List<Feature>();
                f = (Feature)doc.FirstFeature();
                while (f != null)
                {
                    string nm = f.Name ?? string.Empty;
                    if (nm.StartsWith("Boss-Extrude") || nm.StartsWith("Cut-Extrude"))
                        extrudes.Add(f);
                    f = (Feature)f.GetNextFeature();
                }

                for (int i = 0; i < extrudes.Count; i++)
                {
                    if (indexTargets.Contains(i))
                        toDelete.Add(extrudes[i]);
                }
            }

            if (toDelete.Count == 0)
                return "No features found matching: " + string.Join(", ", names);

            doc.ClearSelection2(true);
            foreach (Feature item in toDelete)
                item.Select2(true, 0);

            int opts = (int)swDeleteSelectionOptions_e.swDelete_Absorbed |
                       (int)swDeleteSelectionOptions_e.swDelete_Children;
            doc.Extension.DeleteSelection2(opts);
            doc.ForceRebuild3(false);
            return "OK\nDeleted: " + string.Join(", ", names);
        }

        private string ExecuteDeleteLastN(CadCommandDto command)
        {
            IModelDoc2? doc = EnsurePartDocument(createIfMissing: false);
            if (doc == null)
                return "No active document.";

            int n = command.TargetReference?.LastNCount ?? 1;
            if (n <= 0) n = 1;

            var systemTypes = new HashSet<string>
            {
                "RefPlane", "OriginProfileFeature", "Reference", "HistoryFolder",
                "SelectionSetFolder", "SensorFolder", "MaterialFolder",
                "CommentsFolder", "DesignBinder",
            };

            var all = new List<Feature>();
            Feature f = (Feature)doc.FirstFeature();
            while (f != null)
            {
                if (!systemTypes.Contains(f.GetTypeName2() ?? string.Empty))
                    all.Add(f);
                f = (Feature)f.GetNextFeature();
            }

            int start = Math.Max(0, all.Count - n);
            var toDelete = all.GetRange(start, all.Count - start);

            if (toDelete.Count == 0)
                return "No deletable features found.";

            doc.ClearSelection2(true);
            foreach (Feature item in toDelete)
                item.Select2(true, 0);

            int opts = (int)swDeleteSelectionOptions_e.swDelete_Absorbed |
                       (int)swDeleteSelectionOptions_e.swDelete_Children;
            doc.Extension.DeleteSelection2(opts);
            doc.ForceRebuild3(false);
            string noun = toDelete.Count == 1 ? "feature" : "features";
            return "OK\nDeleted last " + toDelete.Count + " " + noun + ".";
        }

        private static int DeleteGeneratedFeatures(IModelDoc2 doc)
        {
            var deletable = new List<Feature>();
            Feature feat = (Feature)doc.FirstFeature();
            while (feat != null)
            {
                Feature next = (Feature)feat.GetNextFeature();
                string typeName = feat.GetTypeName2() ?? "";

                if (typeName != "RefPlane" &&
                    typeName != "OriginProfileFeature" &&
                    typeName != "Reference" &&
                    typeName != "HistoryFolder" &&
                    typeName != "SelectionSetFolder" &&
                    typeName != "SensorFolder" &&
                    typeName != "MaterialFolder" &&
                    typeName != "CommentsFolder" &&
                    typeName != "DesignBinder")
                {
                    deletable.Add(feat);
                }

                feat = next;
            }

            doc.ClearSelection2(true);
            int selected = 0;
            foreach (Feature item in deletable)
            {
                if (item.Select2(true, 0))
                    selected++;
            }

            if (selected > 0)
            {
                int options = (int)swDeleteSelectionOptions_e.swDelete_Absorbed |
                              (int)swDeleteSelectionOptions_e.swDelete_Children;
                doc.Extension.DeleteSelection2(options);
            }

            doc.ClearSelection2(true);
            return selected;
        }
    }
}
