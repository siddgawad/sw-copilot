# CAD Modeling Fix Plan

**Problem:** Natural language → SolidWorks produces correct geometry but underdefined sketches.

---

## Root Cause Analysis

### Current Flow (Broken)

```
User: "120x80x10mm plate"
  ↓
LLM: {"type": "add_center_rectangle", "length": 120, "width": 80}
  ↓
C#: CreateCornerRectangle(-60, -40, 60, 40)  // Coordinates computed from dimensions
  ↓
Result: Rectangle EXISTS at 120x80 size, but SolidWorks sees:
  - 4 line entities with endpoints
  - NO dimensions
  - NO constraints
  - Sketch is UNDERDEFINED (blue)
```

### Why This Is Wrong

In SolidWorks, a **parametric model** requires:
1. **Geometry** (lines, circles, etc.)
2. **Constraints** (coincident, horizontal, parallel, etc.)
3. **Driving dimensions** (numeric values that control size)

Current code does step 1 only. Steps 2-3 are missing.

### Evidence

In SolidWorks:
- **Black sketch** = fully defined (has dimensions + constraints)
- **Blue sketch** = underdefined (can be dragged/changed)
- Our sketches are blue because they have no driving dimensions

---

## Solution Approaches

### Option A: Add Dimensions After Geometry (Minimal Change)

Keep current LLM output, but C# adds driving dimensions after creating geometry:

```csharp
// Create rectangle
doc.SketchManager.CreateCornerRectangle(x1, y1, 0, x2, y2, 0);

// Select two diagonal points
doc.Select2(false, (int)swSelectType_e.swSelSketchPoints);
doc.Select2(true, (int)swSelectType_e.swSelSketchPoints);

// Add horizontal dimension
doc.SketchManager.AddDimension3(0, 0, 0, 0, 0, 0, "120mm@H");

// Select for vertical dimension
// Add vertical dimension
```

**Pros:** Minimal code change, keeps LLM prompt unchanged  
**Cons:** Need to figure out SolidWorks dimension API (Select2, AddDimension3)

### Option B: Explicit Dimension Entities in Schema

Change LLM output to include dimension operations:

```json
{
  "operations": [
    {"type": "create_sketch", "plane": "Front Plane"},
    {"type": "add_rectangle", "p1": [0, 0], "p2": [1, 1]},
    {"type": "add_dimension", "entity": "rect_1", "type": "horizontal", "value": 120},
    {"type": "add_dimension", "entity": "rect_1", "type": "vertical", "value": 80},
    {"type": "add_constraint", "entity": "rect_1.center", "type": "coincident", "target": "origin"},
    {"type": "extrude_boss", "depth_mm": 10}
  ]
}
```

**Pros:** Explicit, clear intent, LLM knows dimensions  
**Cons:** Requires schema change, LLM prompt update, more operations to execute

### Option C: Use SolidWorks Equations

Instead of dimensions, drive geometry with equations:

```csharp
// Add equation: "D1@Sketch1 = 120mm"
doc.Extension.SetUserPreferenceIntegerValue(...);
```

**Pros:** Parametric, flexible  
**Cons:** More complex, equations are global state

---

## Recommended Approach: Option A

**Reason:** Minimal change to existing code, focuses on fixing the actual bug (missing dimensions) rather than redesigning the schema.

### Implementation Steps

1. **Research SolidWorks dimension API** (1 hour)
   - How to select sketch entities
   - How to add horizontal/vertical dimensions
   - How to add diameter dimensions for circles

2. **Implement `AddDimension` helper** (2 hours)
   ```csharp
   private void AddHorizontalDimension(IModelDoc2 doc, object point1, object point2, double valueMm)
   private void AddVerticalDimension(IModelDoc2 doc, object point1, object point2, double valueMm)
   private void AddDiameterDimension(IModelDoc2 doc, object circle, double valueMm)
   ```

3. **Update operation handlers** (2 hours)
   - `ExecAddCenterRectangle`: add length + width dimensions
   - `ExecAddCircles`: add diameter dimensions
   - `ExecSketch`: handle dimension entities if present

4. **Test in SolidWorks** (1 hour)
   - Verify sketches are black (fully defined)
   - Verify changing dimension value updates geometry
   - Verify no regressions in existing tests

---

## SolidWorks Dimension API Research

Need to answer:

1. **How to select sketch entities?**
   - `doc.Select2(selectIt, (int)swSelectType_e.swSelSketchPoints)`?
   - Or use `ISketchEntity.Select4()`?

2. **How to add linear dimension?**
   - `SketchManager.AddDimension3()`?
   - What are the parameters?

3. **How to add diameter dimension?**
   - `SketchManager.CreateCircleDimension()`?
   - Need example code

### Known API Methods

From SolidWorks Interop:

```csharp
// Selection
doc.Select2(bool Append, int Type)
IEntity.Select4(bool Append, int Mark)

// Dimensions (need to verify)
SketchManager.AddDimension3(double x, double y, double z, ...)
SketchManager.CreateLineDimension(...)
```

---

## Test Plan

After implementation:

```
Test 1: Base plate without holes
Input: "make a 120x80x10mm base plate"
Expected:
  - Sketch has rectangle with 120mm horizontal dimension
  - Sketch has 80mm vertical dimension
  - Sketch is fully defined (black)
  - Extrude is 10mm

Test 2: Base plate with holes
Input: "make a 120x80x10mm plate with four 6mm holes"
Expected:
  - Base sketch: 120mm x 80mm dimensions
  - Hole sketch: 4 circles with 6mm diameter dimension
  - Hole positions constrained (e.g., 10mm from edges)
  
Test 3: Fillet
Input: "add 2mm fillet to all edges"
Expected:
  - Fillet on 4 outer edges only
  - No fillet on hole edges
```

---

## Related Issues

- Fillet edge selection: Need to filter external vs internal edges
- Validation: Should check sketch is fully defined
- LLM prompt: Should mention dimension constraints

---

## Next Steps

1. [ ] Upload `REDTEAM_AUDIT.md` + `AUDIT_REQUEST.md` to GPT-4/Claude
2. [ ] Get working SolidWorks dimension API code
3. [ ] Implement Option A fix
4. [ ] Test in SolidWorks
5. [ ] Update CLAUDE.md with lessons learned
