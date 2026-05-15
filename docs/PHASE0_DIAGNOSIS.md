# Phase 0 Diagnosis — SW Copilot CAD Modeling Audit

**Date:** 2026-05-05  
**Analyst:** Claude Opus 4.7 (Senior CAD Automation Architect)  
**Status:** ✅ Complete

---

## 1. Current Architecture Summary

```
User Prompt → LLM Planner → OperationGraph JSON → C# COM Executor → SolidWorks Part
                   ↓
            Validation Agent → PartReport → Comparison → Repair Loop (if needed)
```

### Key Components

| Component | File | Purpose |
|-----------|------|---------|
| **LLM Planner** | `macro_engineer.py` | Converts natural language to OperationGraph JSON |
| **Deterministic Parser** | `base_plate_v0.py` | Direct compiler for simple base plates (no LLM) |
| **Validation** | `validation_agent.py` | Compares OperationGraph vs PartReport |
| **COM Executor** | `OperationExecutor.cs` | Executes operations via SolidWorks COM |
| **DTOs** | `OperationGraphDto.cs`, `schemas.py` | Shared schema between Python/C# |

---

## 2. Current Operation Schema (v0.2)

### Supported Operations

| Operation | Fields | Notes |
|-----------|--------|-------|
| `create_part` | - | Initialize new part document |
| `create_sketch` | `plane`, `sketch_id` | Opens sketch on plane/face |
| `add_center_rectangle` | `center`, `length`, `width` | Creates rectangle geometry |
| `add_circles` | `circles[]` (center, diameter) | Creates circle geometry |
| `extrude_boss` | `profile_id`, `depth_mm` | Extrudes sketch to create solid |
| `extrude_cut` | `profile_id`, `through_all`, `depth_mm` | Cuts through solid |
| `fillet` | `feature_ids`, `radius_mm` | Fillets selected edges |
| `chamfer` | `feature_ids`, `distance_mm` | Chamfers selected edges |
| `rebuild` | - | Rebuilds part |

### Schema Limitations

**Critical Gap:** No explicit dimension entities in schema. Dimensions are implicit in geometry coordinates.

```json
// Current: dimensions are parameters, NOT SolidWorks dimensions
{"type": "add_center_rectangle", "length": 120, "width": 80}

// What SolidWorks needs: explicit driving dimensions
{"type": "rectangle", ...}
{"type": "dimension", "entity": "rect_1", "axis": "horizontal", "value": 120}
{"type": "dimension", "entity": "rect_1", "axis": "vertical", "value": 80}
```

---

## 3. Where Design Intent Exists

### Backend (Python)

1. **`macro_engineer.py`** - LLM prompt contains:
   - Operation schema definitions (lines 67-175)
   - Engineering reasoning requirements
   - Standards-based dimension derivation rules

2. **`base_plate_v0.py`** - Deterministic parser contains:
   - `parse_design_spec()` - Extracts dimensions from prompt
   - `build_coordinate_plan()` - Computes corner positions
   - `build_operation_graph()` - Generates operations with `length`, `width`, `diameter` values
   - **Design intent stored in:** `DesignSpec.parameters`, `CoordinatePlan.base_rectangle`, `CoordinatePlan.holes`

3. **`models/schemas.py`** - Pydantic models:
   - `AddCenterRectangleOp` (lines 256-271) - has `length`, `width`
   - `AddCirclesOp` (lines 287-298) - has `circles[].diameter`
   - `ExtrudeBossOp` (lines 309-332) - has `depth_mm`
   - **Intent preserved through schema**

### C# Add-in

1. **`OperationGraphDto.cs`** - DTOs:
   - `OperationDto.Length`, `Width`, `DepthMm` (lines 33-40)
   - `CirclePrimitive.Diameter` (line 107)
   - `NamedDimDto` (lines 92-96) - **defined but rarely used**

2. **`OperationExecutor.cs`** - Execution:
   - `ExecAddCenterRectangle()` - uses `op.Length`, `op.Width` to compute corners
   - `ExecAddCircles()` - uses `circle.Diameter` to create circles
   - **Values are used for geometry computation but NOT persisted as dimensions**

---

## 4. Where Design Intent Is Lost

### The Critical Gap

| Stage | What Happens | What's Lost |
|-------|--------------|-------------|
| 1. User input | "120x80x10mm plate" | - |
| 2. LLM/parser | Extracts: length=120, width=80, thickness=10 | - |
| 3. OperationGraph | `{"length": 120, "width": 80}` | - |
| 4. C# Executor | Computes corners: (-60,-40) to (60,40) | **Dimension semantics lost** |
| 5. SolidWorks | `CreateCornerRectangle(-60,-40, 60,40)` | No 120mm or 80mm dimension exists |
| 6. Result | Rectangle IS 120x80 but has NO driving dimension | Sketch is underdefined |

### Root Cause

**Geometry creation ≠ Dimensioning**

The C# code creates geometry at computed coordinates:
```csharp
// OperationExecutor.cs:393-395
doc.SketchManager.CreateCornerRectangle(
    Mm(cx - halfLength), Mm(cy - halfWidth), 0,
    Mm(cx + halfLength), Mm(cy + halfWidth), 0);
```

But **never adds driving dimensions**. SolidWorks sees:
- 4 line entities with endpoints at specific coordinates
- NO dimension entities
- NO constraints (beyond implicit geometric relationships)

The rectangle exists at 120x80 size, but SolidWorks doesn't know it should be locked to those values.

---

## 5. Functions That Create Geometry Without Dimensions

### Backend (deterministic path)

| Function | File | Creates | Missing |
|----------|------|---------|---------|
| `build_operation_graph()` | `base_plate_v0.py:260-324` | Operations with `length`, `width`, `diameter` params | Schema has no dimension entities |

### C# Executor

| Function | File | Creates | Missing |
|----------|------|---------|---------|
| `ExecAddCenterRectangle()` | `OperationExecutor.cs:382-397` | Rectangle at computed corners | No driving dimensions added |
| `ExecAddCircles()` | `OperationExecutor.cs:399-415` | Circles at computed centers/radii | No diameter dimensions added |
| `ExecSketch()` | `OperationExecutor.cs:417-463` | Sketch entities from DTOs | `named_dims` field exists but unused |

---

## 6. Functions That Close Sketches

| Function | File | Behavior |
|----------|------|----------|
| `CloseActiveSketch()` | `OperationExecutor.cs` (not shown in excerpt) | Called after geometry creation |
| `ExecSketch()` | `OperationExecutor.cs:455` | `skMgr.InsertSketch(true)` - closes sketch |
| `ExecExtrudeBoss()` | `OperationExecutor.cs:473-477` | Closes sketch if still active |
| `ExecExtrudeCut()` | `OperationExecutor.cs:514-518` | Closes sketch if still active |

**Problem:** Sketches are closed immediately after geometry creation, before dimensions can be added.

---

## 7. Functions That Register Sketch/Features

| Function | File | What It Registers |
|----------|------|-------------------|
| `RegisterFeature()` | `OperationExecutor.cs` | Registers feature by ID |
| `ExecSketch()` | `OperationExecutor.cs:458-460` | Registers sketch as ProfileFeature |
| `ExecExtrudeBoss()` | `OperationExecutor.cs:501` | Registers extrude feature |
| `ExecExtrudeCut()` | `OperationExecutor.cs:548` | Registers cut feature |

---

## 8. How Fillet Edge Selection Works

### Current Implementation (`SelectEdgesForFillet()`)

**File:** `OperationExecutor.cs:1189-1246`

**Logic:**
1. If `featureIds` is empty (meaning "all edges"):
   - Gets all solid bodies
   - Walks ALL edges of each body
   - Uses COM identity pointer for deduplication
   - Selects each unique edge

2. If `featureIds` is specified:
   - Walks faces of named features
   - Gets edges from each face
   - Selects edges

**Problem:** When selecting "all edges" for a base plate with holes:
- Selects 4 outer perimeter edges (top face)
- Selects 4 outer perimeter edges (bottom face)
- **Also selects** all hole perimeter edges (internal circular edges)
- Fillet fails because it tries to fillet everything together

**User Request:** "all edges" should mean external body edges only, not internal hole edges.

---

## 9. Existing Tests

### Backend Tests

| Test File | Coverage |
|-----------|----------|
| `test_base_plate_v0.py` | 11 tests for deterministic parser |
| `test_macro_engineer_prompt.py` | 21 tests for LLM prompt behavior |
| `test_validation_agent.py` | (not read yet) validation logic |

**Test Results:**
```
11 passed in 1.62s
```

### What Tests Check

- Dimension parsing from prompts ✓
- Coordinate computation ✓
- Operation graph structure ✓
- Validation logic ✓

**What Tests Don't Check:**
- Whether SolidWorks sketches are fully defined
- Whether dimensions exist in the CAD model
- Whether sketches are parametric/editable

---

## 10. Build/Test Commands

### Backend (Python)

```powershell
cd C:\projects\sw-copilot\agent-backend
.venv\Scripts\python -m pytest -q
```

### C# Add-in

```powershell
cd C:\projects\sw-copilot\sw-addin-client
dotnet build SwCopilotAddin.csproj -c Release -p:Platform=x64 -p:RegisterForComInterop=false
```

### Register Add-in (elevated)

```powershell
.\Register-DevAddin.ps1 -BuildConfig Release
```

### Live Test (SolidWorks required)

```
1. Start backend: uvicorn main:app --host 127.0.0.1 --port 8001
2. Open SolidWorks, load add-in
3. Type prompt in chat panel
4. Observe: geometry created, dimensions missing
```

---

## 11. Files Modified Since Last Commit

Based on git status:
- `OperationExecutor.cs` - Updated fillet error message
- New docs added: `REDTEAM_AUDIT.md`, `AUDIT_REQUEST.md`, `CAD_MODELING_FIX.md`
- Branch created: `fix/sketch-dimensions`

---

## 12. Conflict Analysis

### Conflict 1: Schema Has No Dimension Entities

**Problem:** `OperationGraphDto` and `schemas.py` have `named_dims` field but it's not used by executor.

**Impact:** LLM could output dimensions but executor ignores them.

**Fix Required:** Wire `named_dims` into geometry creation OR add dimension creation after geometry.

### Conflict 2: Geometry Created at Coordinates

**Problem:** `ExecAddCenterRectangle` computes corners from `length/width` but doesn't preserve the semantic meaning.

**Impact:** Rectangle is 120x80 but has no "120mm" or "80mm" dimension entity.

**Fix Required:** Add driving dimensions after creating geometry.

### Conflict 3: Sketches Close Before Dimensioning

**Problem:** Flow is: `create_sketch` → `add_center_rectangle` → close sketch → next operation

**Impact:** No opportunity to add dimensions between geometry creation and sketch close.

**Fix Required:** Either delay sketch closing or add dimensions immediately after geometry.

### Conflict 4: `named_dims` Unused

**Problem:** DTO has `NamedDimDto` but `ExecSketch` doesn't apply them.

**Impact:** Even if LLM outputs named dimensions, they're ignored.

**Fix Required:** Implement dimension creation from `named_dims` OR remove the field and use explicit dimension operations.

### Conflict 5: Fillet Selection Too Broad

**Problem:** "All edges" includes internal hole edges.

**Impact:** Fillet fails or produces wrong results.

**Fix Required:** Filter to external perimeter edges only.

---

## 13. Recommended Fix Priority

Based on this analysis:

1. **Add dimension creation helpers** (new methods in `OperationExecutor.cs`)
2. **Wire dimensions into `ExecAddCenterRectangle`** (use helpers)
3. **Wire dimensions into `ExecAddCircles`** (diameter dimensions)
4. **Fix fillet edge selection** (filter external only)
5. **Update validation** (check sketch definition status)

**Do NOT:**
- Redesign entire schema
- Add LLM complexity
- Change deterministic parser output

**DO:**
- Add minimal helper methods
- Modify existing geometry creation functions to call dimension helpers
- Keep changes narrow and testable

---

## Next Phase

Proceed to **Phase 1: Implementation Plan** with specific code changes.
