# AI Code Audit Request

**Project:** SW Copilot - Natural Language to SolidWorks  
**Repo:** https://github.com/siddgawad/sw-copilot  
**Current State:** Live testing found critical issues

---

## What We're Building

Convert natural language → fully-defined parametric SolidWorks part

**Example:**
- Input: `"make a 120x80x10mm base plate with four 6mm holes 10mm from corners"`
- Output: SolidWorks part file with:
  - Base sketch: 120mm × 80mm rectangle (fully dimensioned)
  - Extrusion: 10mm depth
  - Hole sketch: 4 × 6mm diameter circles (positioned)
  - Cut extrusion: through-all

---

## The Critical Bug

**Symptom:** Created parts have correct geometry but sketches show as "underdefined" (blue lines in SolidWorks instead of black).

**Root Cause:** We create sketch geometry at computed coordinates but don't add driving dimensions.

```python
# Current approach (WRONG)
# LLM outputs: rectangle with corners at (-60, -40) to (60, 40)
# C# creates: CreateCornerRectangle(-60, -40, 60, 40)
# Result: Rectangle IS 120x80 but SolidWorks doesn't know it should be locked to those dimensions
```

**What should happen:**
1. Create sketch on Front Plane
2. Draw rectangle (any size initially)
3. Add horizontal dimension: 120mm (driving)
4. Add vertical dimension: 80mm (driving)
5. Add coincident constraint: center at origin
6. Sketch is now fully defined (black)

---

## Specific Questions

### Question 1: SolidWorks Dimension API

What's the correct C# COM code to add driving dimensions?

**Current code:**
```csharp
doc.SketchManager.CreateCornerRectangle(x1, y1, z1, x2, y2, z2);
// Missing: How to add "this width = 120mm" as a driving dimension?
```

**Need:** Working code example for:
- Adding horizontal/vertical dimensions to a rectangle
- Adding diameter dimension to a circle
- Selecting sketch entities for dimensioning

### Question 2: Architecture

Should we:

A. Keep coordinate-based approach but add dimensions after geometry?
B. Change LLM to output explicit dimension entities?
C. Use SolidWorks equations/variables instead of dimensions?

### Question 3: Fillet Failure

```csharp
// Current: selects ALL body edges (including hole edges)
// Fails when hole edges can't take same fillet radius
SelectEdgesForFillet(doc, featureIds: null); // "all edges"
```

How to filter to only external perimeter edges?

---

## Files to Examine

1. **Backend prompt:** `agent-backend/agents/macro_engineer.py`
2. **Deterministic parser:** `agent-backend/agents/base_plate_v0.py`
3. **COM executor:** `sw-addin-client/Execution/OperationExecutor.cs`
4. **Validation:** `agent-backend/agents/validation_agent.py`

---

## Test Cases

| Prompt | Expected | Current |
|--------|----------|---------|
| `make 120x80x10 plate` | Rectangle 120×80 with dimensions | ✓ Size correct, ✗ No dimensions |
| `add 6mm holes` | Circles with 6mm diameter dimension | ✓ Size correct, ✗ No dimension |
| `fillet all edges 2mm` | Fillet on 4 outer edges only | ✗ Fails |

---

## What We Need

1. **Working SolidWorks COM code** for adding driving dimensions to sketches
2. **Opinion on architecture:** coordinates vs explicit dimensions
3. **Edge filtering strategy** for fillet on external edges only

**Please provide code, not just advice.** We need:
- C# code to add horizontal/vertical dimensions
- Strategy for selecting sketch entities
- Filter for external vs internal edges

---

## Success Criteria

After fix:
- [ ] Sketches show as fully defined (black) in SolidWorks
- [ ] Changing dimension value updates geometry (parametric)
- [ ] Fillet works on base plate external edges
- [ ] No LLM repair loops

---

**Upload these files for analysis:**
- This file
- `agent-backend/agents/base_plate_v0.py`
- `sw-addin-client/Execution/OperationExecutor.cs`
- `agent-backend/agents/macro_engineer.py`
