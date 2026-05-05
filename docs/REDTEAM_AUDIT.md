# SW Copilot Red Team Audit

**Date:** 2026-05-05  
**Status:** Critical review needed before beta release

---

## What We're Building

Natural language → SolidWorks part. User types "make a 120x80x10mm base plate with four 6mm holes" and gets a fully-defined parametric CAD model.

## Current Architecture

```
User Prompt → LLM (Groq/NIM/Ollama) → OperationGraph JSON → C# COM Executor → SolidWorks Part
```

### Key Components

1. **Backend** (`agent-backend/`): Python FastAPI server
   - `macro_engineer.py`: LLM prompt for operation planning
   - `base_plate_v0.py`: Deterministic parser for base plate commands
   - `validation_agent.py`: Compares expected vs actual part
   - `standards/dimension_resolver.py`: ISO standard dimensions

2. **C# Add-in** (`sw-addin-client/`): SolidWorks 2021 COM integration
   - `OperationExecutor.cs`: 12 operation types (sketch, extrude, fillet, etc.)
   - `BackendClient.cs`: HTTP client for backend
   - `TaskPaneHost.cs`: Chat UI in SolidWorks

3. **Operation Schema** (v0.2):
   ```json
   {
     "operations": [
       {"type": "create_sketch", "plane": "Front Plane"},
       {"type": "add_center_rectangle", "length": 120, "width": 80},
       {"type": "extrude_boss", "depth_mm": 10},
       {"type": "add_circles", "circles": [...]},
       {"type": "extrude_cut", "through_all": true}
     ]
   }
   ```

## Known Issues (Live Test Findings)

### 1. Sketches Are Underdefined ✗ CRITICAL

**Problem:** Rectangle created at coordinates (-60,-40) to (60,40) but no driving dimensions added. SolidWorks shows sketch as underdefined (blue lines).

**Current behavior:**
```csharp
// Creates geometry at correct size but no dimensions
doc.SketchManager.CreateCornerRectangle(x1, y1, 0, x2, y2, 0);
// Returns "120 x 80 mm" but sketch has no 120mm or 80mm dimension
```

**Expected CAD workflow:**
1. Create sketch on plane
2. Draw rectangle (any size)
3. Add horizontal dimension: 120mm
4. Add vertical dimension: 80mm  
5. Add coincident constraint: center at origin
6. Now sketch is fully defined (black)

**Root cause:** We're creating geometry at computed coordinates but not adding driving dimensions. SolidWorks doesn't know the rectangle should be 120x80 - it just sees points at those coordinates.

### 2. Fillet Fails on "All Edges" ✗ CRITICAL

**Problem:** `add 2mm fillet to all edges` fails with "edges may not support this radius"

**Current behavior:**
- Selects ALL body edges (including internal hole edges)
- Calls `FeatureFillet()` on entire selection
- SolidWorks rejects because hole edges can't be filleted with same radius

**Root cause:** Edge selection includes internal edges (hole perimeters) which may not support the same fillet radius as external edges.

### 3. Validation Axis Mapping ✗ FIXED

**Problem:** Front Plane extrudes map X/Y incorrectly. User's "120x80x10" becomes "120x10x80" in validation.

**Status:** Fixed in `validation_agent.py` - Front Plane now correctly maps sketch X/Y to model X/Y.

### 4. Repair Loop Repeats Same Graph ✗ PARTIALLY FIXED

**Problem:** When operation fails, LLM regenerates identical graph → infinite loop.

**Current fix:** Added `_repair_loop_repeated` detection - appends `_REPAIR_REpetition_NOTE` to prompt forcing different approach.

---

## Fundamental Questions for Red Team Review

### Question 1: Coordinates vs Dimensions

**Current approach:** LLM computes coordinates from natural language dimensions, creates geometry at those coordinates.

**Problem:** This bypasses SolidWorks' parametric modeling. A rectangle from (-60,-40) to (60,40) is NOT the same as "120mm x 80mm rectangle centered at origin" in SolidWorks' parametric system.

**Question:** Should we instead:
A. Keep coordinate approach but add driving dimensions after geometry creation?
B. Change LLM output to explicitly include dimension entities?
C. Use SolidWorks' parametric modeling (equations, variables)?

### Question 2: Operation Granularity

**Current approach:** High-level operations like `add_center_rectangle` that bundle geometry + implied dimensions.

**Problem:** LLM knows intended dimensions (120mm, 80mm) but they're lost as parameters, not SolidWorks dimensions.

**Question:** Should operations be lower-level?
```json
// Current
{"type": "add_center_rectangle", "length": 120, "width": 80}

// Alternative: explicit dimension entities
{"type": "create_rectangle", "p1": [0,0], "p2": [1,1]}
{"type": "add_dimension", "entity": "rect_1", "dimension": "horizontal", "value": 120}
{"type": "add_dimension", "entity": "rect_1", "dimension": "vertical", "value": 80}
```

### Question 3: Sketch → Feature Separation

**Current approach:** Each operation creates geometry AND closes sketch implicitly.

**Problem:** Can't add dimensions between operations. Sketch is closed before dimensioning.

**Question:** Should workflow be explicit?
```
create_sketch → [add_geometry]* → [add_constraints]* → [add_dimensions]* → close_sketch → extrude
```

### Question 4: Error Recovery

**Current approach:** LLM sees error message, regenerates entire operation graph.

**Problem:** LLM often regenerates identical graph → repair loop.

**Question:** Should executor provide structured feedback?
```
Error: extrude_boss failed
Reason: sketch not closed
Suggestion: add missing line segment or close sketch before extrude
```

### Question 5: Deterministic vs LLM

**Current approach:** `base_plate_v0` uses deterministic parser (no LLM). Works for simple prompts.

**Problem:** Can't handle variations ("rectangular plate", "flat bar with holes", etc.)

**Question:** Should deterministic path output OperationGraph directly, while LLM handles complex cases?

---

## Specific Technical Questions

### SolidWorks COM Specific

1. **Dimension API:** What's the correct way to add driving dimensions?
   - `SketchManager.AddDimension3()`?
   - `SketchManager.CreateLineDimension()`?
   - Need example code for dimensioning a rectangle

2. **Sketch entity selection:** How to select sketch entities for dimensioning?
   - Need to select specific points/lines
   - `doc.Select2()` with entity pointers?

3. **Fillet edge selection:** How to select only external edges?
   - Current: walks all body edges
   - Need: filter to perimeter edges only

### Architecture

4. **Schema version:** Should v0.3 include explicit dimension entities?

5. **Validation:** Should validation check sketch is fully defined (black)?

6. **Traces:** Should run artifacts include sketch entity IDs for debugging?

---

## Test Cases That Should Work

| Prompt | Expected | Current Status |
|--------|----------|----------------|
| make a 120x80x10mm base plate | Rectangle 120x80, extruded 10mm | ✓ Geometry correct, ✗ No dimensions |
| add four 6mm holes | 4 circles, 6mm diameter | ✓ Geometry correct, ✗ No diameter dimension |
| add 2mm fillet to all edges | Fillet on 4 outer edges | ✗ Fails |
| make a circle 30mm extrude 30mm | Circle 30mm diameter (not radius) | ✓ Fixed (diameter default) |

---

## Request for Red Team

Please review:

1. **Is the coordinate-based approach fundamentally broken?** Should we redesign the operation schema?

2. **What's the minimal fix** to make sketches fully defined? (AddDimension calls? Different sketch approach?)

3. **How should SolidWorks COM dimensioning work** in this context? Need working code example.

4. **Is the validation approach correct?** Comparing OperationGraph → PartReport

5. **What's the simplest path** to "add 2mm fillet to all edges" working reliably?

---

## Files to Review

- `agent-backend/agents/macro_engineer.py` - LLM prompt
- `agent-backend/agents/base_plate_v0.py` - Deterministic parser
- `sw-addin-client/Execution/OperationExecutor.cs` - COM execution
- `docs/INTENT_TO_JSON_STRATEGY.md` - Design rationale

---

**Next step:** Upload this to GPT-4/Claude with request for specific code fixes, not just advice.
