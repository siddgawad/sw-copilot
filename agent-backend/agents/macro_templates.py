"""Deterministic SolidWorks macro templates for common CAD commands."""

from __future__ import annotations

import re
from dataclasses import dataclass


_DIMENSION_RE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>mm|millimeters?|millimetres?|cm|centimeters?|centimetres?|m|meters?|metres?|inches?|inch|in|\")?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Dimension:
    metres: float
    millimetres: float


def try_generate_template(prompt: str) -> str | None:
    text = _normalise(prompt)

    # ── Delete-specific-feature (highest priority — must run before extrude checks) ──
    if _is_delete_named_feature_command(text):
        numbers = _parse_feature_numbers(text)
        if numbers:
            return _delete_named_features_macro(numbers)

    if _is_delete_last_command(text):
        n = _parse_last_n(text)
        return _delete_last_n_features_macro(n)

    clear_first = _is_delete_command(text)

    if _is_cube_command(text):
        size = _first_dimension(text)
        if size is not None:
            return _rectangular_prism_macro(
                size.metres,
                size.metres,
                size.metres,
                "Created a {0:g} mm cube.".format(size.millimetres),
                text,
                clear_first,
            )

    if _is_rectangular_prism_command(text):
        dims = _rectangular_prism_dimensions(text)
        if dims is not None:
            length, width, height = dims
            message = "Created a {0:g} mm x {1:g} mm x {2:g} mm rectangular prism.".format(
                length.millimetres,
                width.millimetres,
                height.millimetres,
            )
            return _rectangular_prism_macro(length.metres, width.metres, height.metres, message, text, clear_first)

    if _is_cylinder_command(text):
        dims = _cylinder_dimensions(text)
        if dims is not None:
            radius, height, diameter_mm = dims
            message = "Created a {0:g} mm diameter x {1:g} mm tall cylinder.".format(
                diameter_mm,
                height.millimetres,
            )
            return _cylinder_macro(radius.metres, height.metres, message, text, clear_first)

    if _is_extrude_existing_command(text):
        distance = _named_dimension(text, ("extrude", "extruded", "height", "depth", "tall", "thick", "thickness"))
        if distance is None:
            distance = _first_dimension(text)
        if distance is not None:
            return _extrude_existing_sketch_macro(distance.metres, "Extruded selected or latest sketch {0:g} mm.".format(distance.millimetres))

    if clear_first:
        return _delete_all_features_macro()

    return None


def _normalise(prompt: str) -> str:
    return " ".join(prompt.lower().replace("×", " x ").split())


def _is_delete_command(text: str) -> bool:
    has_action = any(word in text for word in ("delete", "remove", "clear", "erase", "reset", "wipe"))
    has_target = any(word in text for word in ("all", "everything", "model", "body", "bodies", "feature", "features", "sketch", "sketches"))
    return has_action and has_target


def _is_cube_command(text: str) -> bool:
    return "cube" in text


def _is_rectangular_prism_command(text: str) -> bool:
    has_shape = any(word in text for word in ("rectangular prism", "rectangle", "rectangular", "block", "prism"))
    has_extrude = any(word in text for word in ("extrude", "extruded", "height", "depth", "tall", "thick", "thickness"))
    return has_shape and has_extrude


_FACE_WORDS = frozenset({"face", "surface", "top of", "bottom of", "side of"})


def _is_cylinder_command(text: str) -> bool:
    # Face-qualified requests must go to Groq (which has GetFaces() guidance); the
    # template can only target named planes, not dynamic face selections.
    if any(w in text for w in _FACE_WORDS):
        return False
    return "cylinder" in text or ("circle" in text and any(word in text for word in ("extrude", "height", "depth", "tall")))


def _is_extrude_existing_command(text: str) -> bool:
    if "extrude" not in text and "extruded" not in text:
        return False

    # Delete intent always overrides: "delete boss extrude 5" is not an extrude command.
    if _is_delete_named_feature_command(text) or _is_delete_last_command(text):
        return False

    # If a new primitive is requested, another deterministic template should own it.
    new_shape_words = ("cube", "cylinder", "circle", "rectangle", "rectangular", "block", "prism")
    if any(word in text for word in new_shape_words):
        return False

    return True


# ── Delete-by-name and delete-last helpers ────────────────────────────────────

# Matches standalone integers NOT immediately followed by a unit suffix.
# "delete boss extrude 5 and 6" → [5, 6]   "extrude 50 mm" → [] (50 filtered by unit)
_BARE_INT_RE = re.compile(
    r"\b(\d+)\b(?!\s*(?:mm|cm|m\b|in\b|inch|\"|\.\d))",
    re.IGNORECASE,
)


def _is_delete_named_feature_command(text: str) -> bool:
    has_delete  = any(w in text for w in ("delete", "remove"))
    has_feature = any(w in text for w in ("boss", "extrude", "cut", "sketch", "fillet",
                                           "chamfer", "pattern", "mirror", "feature"))
    has_number  = bool(_BARE_INT_RE.search(text))
    return has_delete and has_feature and has_number


def _is_delete_last_command(text: str) -> bool:
    has_delete = any(w in text for w in ("delete", "remove", "undo"))
    has_last   = any(w in text for w in ("last", "latest", "recent", "previous"))
    return has_delete and has_last


def _parse_feature_numbers(text: str) -> list[int]:
    """Return all bare integers in text, used as Boss-Extrude feature indices."""
    return [int(m.group(1)) for m in _BARE_INT_RE.finditer(text)]


def _parse_last_n(text: str) -> int:
    """Return N from 'delete last N features', defaulting to 1."""
    m = re.search(r"\blast\s+(\d+)\b", text)
    return int(m.group(1)) if m else 1


def _rectangular_prism_dimensions(text: str) -> tuple[Dimension, Dimension, Dimension] | None:
    values = _all_dimensions(text)
    if len(values) < 2:
        return None

    length = _named_dimension(text, ("length", "long")) or values[0]
    width = _named_dimension(text, ("width", "breadth", "wide")) or values[1]
    height = _named_dimension(text, ("extrude", "extruded", "height", "depth", "tall", "thick", "thickness"))
    if height is None:
        height = values[2] if len(values) >= 3 else values[-1]

    return length, width, height


def _cylinder_dimensions(text: str) -> tuple[Dimension, Dimension, float] | None:
    values = _all_dimensions(text)
    if not values:
        return None

    radius = _named_dimension(text, ("radius", "r"))
    diameter = _named_dimension(text, ("diameter", "dia"))
    if radius is None:
        if diameter is None:
            diameter = values[0]
        radius = Dimension(diameter.metres / 2.0, diameter.millimetres / 2.0)
    diameter_mm = radius.millimetres * 2.0

    height = _named_dimension(text, ("extrude", "extruded", "height", "depth", "tall", "thick", "thickness"))
    if height is None:
        height = values[1] if len(values) >= 2 else values[0]

    return radius, height, diameter_mm


def _first_dimension(text: str) -> Dimension | None:
    values = _all_dimensions(text)
    return values[0] if values else None


def _all_dimensions(text: str) -> list[Dimension]:
    return [_to_dimension(match.group("value"), match.group("unit")) for match in _DIMENSION_RE.finditer(text)]


def _named_dimension(text: str, names: tuple[str, ...]) -> Dimension | None:
    name_pattern = "|".join(re.escape(name) for name in names)
    value_pattern = _DIMENSION_RE.pattern

    after = re.search(rf"\b(?:{name_pattern})\b\s*(?:of|=|:|is|it)?\s*{value_pattern}", text, re.IGNORECASE)
    if after:
        return _to_dimension(after.group("value"), after.group("unit"))

    before = re.search(rf"{value_pattern}\s*\b(?:{name_pattern})\b", text, re.IGNORECASE)
    if before:
        return _to_dimension(before.group("value"), before.group("unit"))

    return None


def _to_dimension(value: str, unit: str | None) -> Dimension:
    amount = float(value)
    unit_name = (unit or "mm").lower()
    if unit_name in ("mm", "millimeter", "millimeters", "millimetre", "millimetres"):
        metres = amount / 1000.0
    elif unit_name in ("cm", "centimeter", "centimeters", "centimetre", "centimetres"):
        metres = amount / 100.0
    elif unit_name in ("m", "meter", "meters", "metre", "metres"):
        metres = amount
    elif unit_name in ("in", "inch", "inches", '"'):
        metres = amount * 0.0254
    else:
        metres = amount / 1000.0
    return Dimension(metres=metres, millimetres=metres * 1000.0)


def _plane_name(text: str) -> str:
    if "front plane" in text:
        return "Front Plane"
    if "right plane" in text:
        return "Right Plane"
    return "Top Plane"


def _cs(value: float) -> str:
    return f"{value:.9f}".rstrip("0").rstrip(".")


def _rectangular_prism_macro(length: float, width: float, height: float, message: str, text: str, clear_first: bool) -> str:
    plane = _plane_name(text)
    half_length = length / 2.0
    half_width = width / 2.0
    clear_call = "DeleteGeneratedFeatures(doc);" if clear_first else ""
    helper = _delete_helper_method() if clear_first else ""
    return f"""using System;
using System.Collections.Generic;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;

public class Macro
{{
    public static void Run(SolidWorks.Interop.sldworks.ISldWorks swApp)
    {{
        IModelDoc2 doc = (IModelDoc2)swApp.ActiveDoc;
        if (doc == null)
        {{
            swApp.NewPart();
            doc = (IModelDoc2)swApp.ActiveDoc;
        }}
        if (doc == null)
        {{
            Console.WriteLine("No active part document.");
            return;
        }}

        if (doc.GetType() != (int)swDocumentTypes_e.swDocPART)
        {{
            Console.WriteLine("Active document is not a part.");
            return;
        }}

        {clear_call}
        doc.ClearSelection2(true);
        bool selected = doc.Extension.SelectByID2("{plane}", "PLANE", 0, 0, 0, false, 0, null, 0);
        if (!selected)
        {{
            Console.WriteLine("Could not select {plane}.");
            return;
        }}

        SketchManager sketchMgr = doc.SketchManager;
        sketchMgr.InsertSketch(true);
        sketchMgr.CreateCornerRectangle(-{_cs(half_length)}, -{_cs(half_width)}, 0, {_cs(half_length)}, {_cs(half_width)}, 0);
        sketchMgr.InsertSketch(true);

        FeatureManager featMgr = doc.FeatureManager;
        Feature feature = featMgr.FeatureExtrusion2(
            true, false, false,
            (int)swEndConditions_e.swEndCondBlind, 0,
            {_cs(height)}, 0.0,
            false, false, false, false,
            0.0, 0.0,
            false, false, false, false,
            true, true, true,
            0, 0.0, false);

        if (feature == null)
        {{
            Console.WriteLine("Extrude failed.");
            return;
        }}

        doc.ForceRebuild3(false);
        Console.WriteLine("{message}");
    }}

{helper}
}}
"""


def _cylinder_macro(radius: float, height: float, message: str, text: str, clear_first: bool) -> str:
    plane = _plane_name(text)
    clear_call = "DeleteGeneratedFeatures(doc);" if clear_first else ""
    helper = _delete_helper_method() if clear_first else ""
    return f"""using System;
using System.Collections.Generic;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;

public class Macro
{{
    public static void Run(SolidWorks.Interop.sldworks.ISldWorks swApp)
    {{
        IModelDoc2 doc = (IModelDoc2)swApp.ActiveDoc;
        if (doc == null)
        {{
            swApp.NewPart();
            doc = (IModelDoc2)swApp.ActiveDoc;
        }}
        if (doc == null)
        {{
            Console.WriteLine("No active part document.");
            return;
        }}

        if (doc.GetType() != (int)swDocumentTypes_e.swDocPART)
        {{
            Console.WriteLine("Active document is not a part.");
            return;
        }}

        {clear_call}
        doc.ClearSelection2(true);
        bool selected = doc.Extension.SelectByID2("{plane}", "PLANE", 0, 0, 0, false, 0, null, 0);
        if (!selected)
        {{
            Console.WriteLine("Could not select {plane}.");
            return;
        }}

        SketchManager sketchMgr = doc.SketchManager;
        sketchMgr.InsertSketch(true);
        sketchMgr.CreateCircleByRadius(0.0, 0.0, 0.0, {_cs(radius)});
        sketchMgr.InsertSketch(true);

        FeatureManager featMgr = doc.FeatureManager;
        Feature feature = featMgr.FeatureExtrusion2(
            true, false, false,
            (int)swEndConditions_e.swEndCondBlind, 0,
            {_cs(height)}, 0.0,
            false, false, false, false,
            0.0, 0.0,
            false, false, false, false,
            true, true, true,
            0, 0.0, false);

        if (feature == null)
        {{
            Console.WriteLine("Extrude failed.");
            return;
        }}

        doc.ForceRebuild3(false);
        Console.WriteLine("{message}");
    }}

{helper}
}}
"""


def _extrude_existing_sketch_macro(distance: float, message: str) -> str:
    return f"""using System;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;

public class Macro
{{
    public static void Run(SolidWorks.Interop.sldworks.ISldWorks swApp)
    {{
        IModelDoc2 doc = (IModelDoc2)swApp.ActiveDoc;
        if (doc == null)
        {{
            Console.WriteLine("No active document.");
            return;
        }}

        if (doc.GetType() != (int)swDocumentTypes_e.swDocPART)
        {{
            Console.WriteLine("Active document is not a part.");
            return;
        }}

        TryCloseActiveSketch(doc);

        ISelectionMgr selMgr = doc.ISelectionManager;
        if (selMgr == null || selMgr.GetSelectedObjectCount2(-1) == 0)
        {{
            Feature sketch = SelectMostRecentSketch(doc);
            if (sketch == null)
            {{
                Console.WriteLine("No selected or existing sketch found to extrude.");
                return;
            }}
        }}

        FeatureManager featMgr = doc.FeatureManager;
        Feature feature = featMgr.FeatureExtrusion2(
            true, false, false,
            (int)swEndConditions_e.swEndCondBlind, 0,
            {_cs(distance)}, 0.0,
            false, false, false, false,
            0.0, 0.0,
            false, false, false, false,
            true, true, true,
            0, 0.0, false);

        if (feature == null)
        {{
            Console.WriteLine("Extrude failed. Select a closed sketch/profile and try again.");
            return;
        }}

        doc.ForceRebuild3(false);
        Console.WriteLine("{message}");
    }}

    private static void TryCloseActiveSketch(IModelDoc2 doc)
    {{
        try
        {{
            SketchManager sketchMgr = doc.SketchManager;
            if (sketchMgr != null && sketchMgr.ActiveSketch != null)
            {{
                sketchMgr.InsertSketch(true);
            }}
        }}
        catch
        {{
        }}
    }}

    private static Feature SelectMostRecentSketch(IModelDoc2 doc)
    {{
        Feature latestSketch = null;
        Feature feat = (Feature)doc.FirstFeature();
        while (feat != null)
        {{
            string typeName = feat.GetTypeName2() ?? "";
            if (typeName == "ProfileFeature" || typeName == "3DProfileFeature")
            {{
                latestSketch = feat;
            }}
            feat = (Feature)feat.GetNextFeature();
        }}

        if (latestSketch != null)
        {{
            doc.ClearSelection2(true);
            latestSketch.Select2(false, 0);
        }}

        return latestSketch;
    }}
}}
"""


def _delete_all_features_macro() -> str:
    return """using System;
using System.Collections.Generic;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;

public class Macro
{
    public static void Run(SolidWorks.Interop.sldworks.ISldWorks swApp)
    {
        IModelDoc2 doc = (IModelDoc2)swApp.ActiveDoc;
        if (doc == null)
        {
            Console.WriteLine("No active document.");
            return;
        }

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
            {
                selected++;
            }
        }

        int deleted = 0;
        if (selected > 0)
        {
            int options = (int)swDeleteSelectionOptions_e.swDelete_Absorbed |
                          (int)swDeleteSelectionOptions_e.swDelete_Children;
            if (doc.Extension.DeleteSelection2(options))
            {
                deleted = selected;
            }
        }

        doc.ClearSelection2(true);
        doc.ForceRebuild3(false);
        Console.WriteLine("Deleted " + deleted + " sketches/features.");
    }
}
"""


def _delete_helper_method() -> str:
    return """    private static void DeleteGeneratedFeatures(IModelDoc2 doc)
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
        foreach (Feature item in deletable)
        {
            item.Select2(true, 0);
        }

        if (deletable.Count > 0)
        {
            int options = (int)swDeleteSelectionOptions_e.swDelete_Absorbed |
                          (int)swDeleteSelectionOptions_e.swDelete_Children;
            doc.Extension.DeleteSelection2(options);
        }

        doc.ClearSelection2(true);
    }
"""


# ── Delete named features (e.g. Boss-Extrude5, Boss-Extrude6) ─────────────────

def _delete_named_features_macro(numbers: list[int]) -> str:
    # Build both name-based and index-based lookup so either works.
    name_set   = ", ".join(f'"Boss-Extrude{n}", "Cut-Extrude{n}"' for n in numbers)
    index_list = ", ".join(str(n - 1) for n in numbers)   # convert to 0-based
    noun       = "feature" if len(numbers) == 1 else "features"
    labels     = ", ".join(f"Boss-Extrude{n}" for n in numbers)
    return f"""using System;
using System.Collections.Generic;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;

public class Macro
{{
    public static void Run(SolidWorks.Interop.sldworks.ISldWorks swApp)
    {{
        IModelDoc2 doc = (IModelDoc2)swApp.ActiveDoc;
        if (doc == null) {{ Console.WriteLine("No active document."); return; }}

        // Primary: match by SolidWorks default feature name.
        var nameTargets = new HashSet<string> {{ {name_set} }};
        var toDelete = new List<Feature>();

        Feature f = (Feature)doc.FirstFeature();
        while (f != null)
        {{
            if (nameTargets.Contains(f.Name ?? "")) toDelete.Add(f);
            f = (Feature)f.GetNextFeature();
        }}

        // Fallback: match by 0-based position among boss/cut extrudes.
        if (toDelete.Count == 0)
        {{
            var idxTargets = new HashSet<int> {{ {index_list} }};
            var extrudes   = new List<Feature>();
            f = (Feature)doc.FirstFeature();
            while (f != null)
            {{
                string nm = f.Name ?? "";
                if (nm.StartsWith("Boss-Extrude") || nm.StartsWith("Cut-Extrude"))
                    extrudes.Add(f);
                f = (Feature)f.GetNextFeature();
            }}
            foreach (int idx in idxTargets)
                if (idx >= 0 && idx < extrudes.Count)
                    toDelete.Add(extrudes[idx]);
        }}

        if (toDelete.Count == 0)
        {{
            Console.WriteLine("No matching {noun} found for: {labels}");
            return;
        }}

        doc.ClearSelection2(true);
        foreach (Feature item in toDelete) item.Select2(true, 0);
        int opts = (int)swDeleteSelectionOptions_e.swDelete_Absorbed |
                   (int)swDeleteSelectionOptions_e.swDelete_Children;
        doc.Extension.DeleteSelection2(opts);
        doc.ForceRebuild3(false);
        Console.WriteLine("Deleted {noun}: {labels}.");
    }}
}}
"""


# ── Delete last N user-created features ───────────────────────────────────────

def _delete_last_n_features_macro(n: int = 1) -> str:
    noun = "feature" if n == 1 else f"{n} features"
    return f"""using System;
using System.Collections.Generic;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;

public class Macro
{{
    public static void Run(SolidWorks.Interop.sldworks.ISldWorks swApp)
    {{
        IModelDoc2 doc = (IModelDoc2)swApp.ActiveDoc;
        if (doc == null) {{ Console.WriteLine("No active document."); return; }}

        var systemTypes = new HashSet<string>
        {{
            "RefPlane", "OriginProfileFeature", "Reference", "HistoryFolder",
            "SelectionSetFolder", "SensorFolder", "MaterialFolder",
            "CommentsFolder", "DesignBinder"
        }};

        var all = new List<Feature>();
        Feature f = (Feature)doc.FirstFeature();
        while (f != null)
        {{
            if (!systemTypes.Contains(f.GetTypeName2() ?? "")) all.Add(f);
            f = (Feature)f.GetNextFeature();
        }}

        int start    = Math.Max(0, all.Count - {n});
        var toDelete = all.GetRange(start, all.Count - start);

        if (toDelete.Count == 0)
        {{
            Console.WriteLine("No deletable features found.");
            return;
        }}

        doc.ClearSelection2(true);
        foreach (Feature item in toDelete) item.Select2(true, 0);
        int opts = (int)swDeleteSelectionOptions_e.swDelete_Absorbed |
                   (int)swDeleteSelectionOptions_e.swDelete_Children;
        doc.Extension.DeleteSelection2(opts);
        doc.ForceRebuild3(false);
        Console.WriteLine("Deleted last {noun}.");
    }}
}}
"""
