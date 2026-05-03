"""Curated SolidWorks 2021 API reference snippets for macro generation.

This is intentionally small and local. The backend should not depend on live web
access while SolidWorks is waiting for a macro, but the LLM still needs concrete
API patterns to avoid inventing COM members that do not exist in SW 2021.
"""

from __future__ import annotations


_ALWAYS_INCLUDE = """\
SOLIDWORKS 2021 API HELP GROUND RULES
- Use IModelDoc2 for document-level operations:
  IModelDoc2 doc = (IModelDoc2)swApp.ActiveDoc;
  SketchManager sketchMgr = doc.SketchManager;
  FeatureManager featMgr = doc.FeatureManager;
  IModelDocExtension ext = doc.Extension;
- Select named planes/features through IModelDocExtension.SelectByID2:
  bool ok = doc.Extension.SelectByID2("Top Plane", "PLANE", 0, 0, 0, false, 0, null, 0);
  The first argument is a string name, not an int enum.
- Start and finish a sketch with SketchManager.InsertSketch(true). There is no
  SketchManager.CreateSketch method in the SW 2021 interop runtime.
- Units are metres. 10 mm = 0.010, 40 mm = 0.040, 50 mm = 0.050.
- Rebuild with doc.ForceRebuild3(false) or doc.EditRebuild3().

FORBIDDEN / HALLUCINATED MEMBERS
- Do not use IPartDoc.SketchManager, IPartDoc.FeatureManager, IPartDoc.ClearSelection2,
  or IPartDoc.ForceRebuild3. Cast ActiveDoc to IModelDoc2 for these.
- Do not use FeatureManager.FeatureCount, SketchManager.SketchCount,
  SketchManager.DeleteSketch, FeatureManager.FeatureManager, BaseFeature,
  CreateExtrudeFeatureData, IExtrudeFeatureData.SetProfile, DirectionType,
  Distance1, swExtrudeDirectionType_e, swFeatureRebuildOptions_e, or
  FeatureManager.FeatureRebuild3.
"""


_NEW_PART = """\
NEW PART / ACTIVE DOCUMENT PATTERN
IModelDoc2 doc = (IModelDoc2)swApp.ActiveDoc;
if (doc == null)
{
    swApp.NewPart();
    doc = (IModelDoc2)swApp.ActiveDoc;
}
if (doc == null)
{
    Console.WriteLine("No active part document.");
    return;
}
"""


_SKETCH_RECTANGLE = """\
SKETCH RECTANGLE PATTERN
doc.ClearSelection2(true);
bool selected = doc.Extension.SelectByID2("Top Plane", "PLANE", 0, 0, 0, false, 0, null, 0);
if (!selected) throw new InvalidOperationException("Could not select Top Plane.");

SketchManager sketchMgr = doc.SketchManager;
sketchMgr.InsertSketch(true);
sketchMgr.CreateCornerRectangle(-0.020, -0.025, 0, 0.020, 0.025, 0);
sketchMgr.InsertSketch(true);

Notes:
- CreateCornerRectangle(x1, y1, z1, x2, y2, z2) creates the rectangle from two corners.
- Use CreateCenterRectangle(cx, cy, cz, cornerX, cornerY, cornerZ) if the prompt asks
  for a centre-defined rectangle.
"""


_EXTRUDE = """\
BLIND EXTRUDE PATTERN
FeatureManager featMgr = doc.FeatureManager;
Feature feat = featMgr.FeatureExtrusion2(
    true, false, false,
    (int)swEndConditions_e.swEndCondBlind, 0,
    0.050, 0.0,
    false, false, false, false,
    0.0, 0.0,
    false, false, false, false,
    true, true, true,
    0, 0.0, false);
if (feat == null) throw new InvalidOperationException("Extrude failed.");

Notes:
- Call this after exiting the sketch.
- The first depth value is in metres.
- Use swEndConditions_e.swEndCondBlind for fixed-depth extrudes.
"""


_FEATURE_TRAVERSAL_DELETE = """\
FEATURE TRAVERSAL / DELETE PATTERN
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
foreach (Feature item in deletable)
{
    item.Select2(true, 0);
}
int options = (int)swDeleteSelectionOptions_e.swDelete_Absorbed |
              (int)swDeleteSelectionOptions_e.swDelete_Children;
bool deleted = deletable.Count == 0 || doc.Extension.DeleteSelection2(options);

Notes:
- Do not count features with FeatureManager.FeatureCount.
- Do not delete sketches through SketchManager.DeleteSketch. Select Feature objects and
  delete through IModelDocExtension.DeleteSelection2.
"""


_CIRCLES = """\
SKETCH CIRCLE PATTERN
SketchManager sketchMgr = doc.SketchManager;
sketchMgr.InsertSketch(true);
sketchMgr.CreateCircleByRadius(0.0, 0.0, 0.0, 0.010);
sketchMgr.InsertSketch(true);

Notes:
- Circle radius is in metres.
- Select the sketch plane before InsertSketch(true).
"""


_FACE_SKETCH = """\
FACE SELECTION PATTERN — sketching on an existing face
NEVER use: doc.Extension.SelectByID2("Face<1>@...", "FACE", ...) — face names are dynamic and will fail.
ALWAYS use GetFaces() + bounding-box traversal:

// 1. Get the last feature in the tree.
Feature lastFeat = null;
Feature fIter = (Feature)doc.FirstFeature();
while (fIter != null) { lastFeat = fIter; fIter = (Feature)fIter.GetNextFeature(); }
if (lastFeat == null) throw new InvalidOperationException("No features found.");

// 2. Enumerate its faces.
object[] faceArr = (object[])lastFeat.GetFaces();
if (faceArr == null || faceArr.Length == 0)
    throw new InvalidOperationException("Feature returned no selectable faces.");

// 3. Find the desired face by bounding-box midpoint.
//    GetBox() returns double[6]: [xMin, yMin, zMin, xMax, yMax, zMax] in metres.
//    TOP face    → maximum (box[1] + box[4]) / 2   (highest Y)
//    BOTTOM face → minimum (box[1] + box[4]) / 2   (lowest Y)
//    FRONT face  → minimum (box[2] + box[5]) / 2   (most negative Z)
//    BACK face   → maximum (box[2] + box[5]) / 2
Face2 targetFace = null;
double extremeVal = double.MinValue;   // use double.MaxValue for minimum searches
foreach (object o in faceArr)
{
    Face2 face = (Face2)o;
    double[] box = (double[])face.GetBox();
    double midY = (box[1] + box[4]) / 2.0;
    if (midY > extremeVal) { extremeVal = midY; targetFace = face; }
}

// 4. Select the face and open a sketch on it.
doc.ClearSelection2(true);
targetFace.Select2(false, null);
doc.SketchManager.InsertSketch(true);

// 5. Draw in sketch coordinates.
//    (0, 0, 0) = global origin projected onto the face plane.
//    For a horizontal face, this is usually near the body centroid — safe default.
doc.SketchManager.CreateCircleByRadius(0.0, 0.0, 0.0, 0.025); // 25 mm radius example

// 6. Close sketch and extrude.
doc.SketchManager.InsertSketch(true);
doc.FeatureManager.FeatureExtrusion2(
    true, false, false,
    (int)swEndConditions_e.swEndCondBlind, 0,
    0.020, 0.0,
    false, false, false, false,
    0.0, 0.0, false, false, false, false,
    true, true, true, 0, 0.0, false);
doc.ForceRebuild3(false);
"""


_CUTS = """\
CUT EXTRUDE PATTERN
FeatureManager featMgr = doc.FeatureManager;
Feature cut = featMgr.FeatureCut3(
    true, false, false,
    (int)swEndConditions_e.swEndCondThroughAll,
    (int)swEndConditions_e.swEndCondBlind,
    0.0, 0.0,
    false, false, false, false,
    0.0, 0.0,
    false, false, false, false,
    false, true, true, true, true, false,
    0, 0.0, false);
if (cut == null) throw new InvalidOperationException("Cut extrude failed.");
"""


def get_api_reference(prompt: str) -> str:
    """Return relevant SolidWorks API snippets for a natural-language request."""
    lowered = prompt.lower()
    sections = [_ALWAYS_INCLUDE, _NEW_PART]

    if any(word in lowered for word in ("sketch", "rectangle", "square", "cube", "block", "extrude", "prism")):
        sections.append(_SKETCH_RECTANGLE)

    if any(word in lowered for word in ("extrude", "cube", "block", "prism", "boss")):
        sections.append(_EXTRUDE)

    if any(word in lowered for word in ("delete", "clear", "remove", "feature", "features", "sketches", "model")):
        sections.append(_FEATURE_TRAVERSAL_DELETE)

    if any(word in lowered for word in ("circle", "cylinder", "hole", "shaft", "round")):
        sections.append(_CIRCLES)

    if any(word in lowered for word in ("cut", "hole", "slot", "remove material")):
        sections.append(_CUTS)

    if any(word in lowered for word in ("top", "bottom", "face", "on top", "on the top",
                                         "on bottom", "on the face", "existing face",
                                         "face of", "top of", "bottom of")):
        sections.append(_FACE_SKETCH)

    return "\n\n".join(sections)
