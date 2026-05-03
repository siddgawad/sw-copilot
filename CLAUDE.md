# SW Copilot â€” Project State (Single Source of Truth)

**Both Claude and Codex must read this entire file before touching any code.**
Both agents have full filesystem access. Read the actual files â€” don't guess at state.
Update the relevant section whenever you complete, break, or discover something new.

---

## What This Is

A standards-grounded AI add-in for SolidWorks 2021.
Natural language â†’ LLM operation planner â†’ validated JSON graph â†’ deterministic C# COM executor.

The LLM is a compiler frontend. The C# executor is the backend. ISO standards data is the type system.
This is NOT "make LLM understand CAD." Reliability comes from determinism at every layer after the LLM.

**Execution pipeline (in order, never skip a layer):**
1. `standards/dimension_resolver.py` â€” exact ISO 273/4762 numbers injected before LLM sees the prompt
2. `rag/` (ChromaDB) â€” explanatory engineering text retrieved and injected (semantic, NOT for exact numbers)
3. `agents/macro_engineer.py` â€” LLM emits OperationGraph JSON with a reasoning scratchpad
4. Pydantic validation (Python) + DTO validation (C#) â€” schema enforced before any execution
5. `OperationExecutor.ValidateGraph()` â€” geometric rule engine refuses impossibilities before COM
6. `OperationExecutor.Execute()` â€” deterministic SolidWorks COM calls, 12 operation types
7. Post-execution validation â€” TODO Week 2 (Codex task)

---

## How the Two Agents Coordinate

- **Claude** owns the Python backend (`agent-backend/`), schemas, RAG, standards data, tests, docs.
- **Codex** owns the C# add-in (`sw-addin-client/`), COM execution, UI, packaging, live SW testing.
- **Shared boundary**: `models/schemas.py` (Python) â†” `Client/OperationGraphDto.cs` (C#) must stay in sync.
  When either agent changes the operation schema, they write to the Handoff Queue below and the other agent mirrors it.
- **Communication**: write to Handoff Queue in this file. The other agent reads CLAUDE.md before every session.
- **Git**: both agents commit to the same repo at `C:\projects\sw-copilot\` (root). Commit after every meaningful change.

---

## Repository Layout â€” Read These Files Directly

```
C:\projects\sw-copilot\                          â† git repo root
â”œâ”€â”€ CLAUDE.md                            â† THIS FILE. Both agents update it.
â”œâ”€â”€ .gitignore
â”‚
â”œâ”€â”€ agent-backend\                       â† Python FastAPI backend (Claude owns)
â”‚   â”œâ”€â”€ main.py                          â† FastAPI app: /generate /ingest /health /version
â”‚   â”œâ”€â”€ config.py                        â† Settings from .env: GROQ_API_KEY, groq_model, etc.
â”‚   â”œâ”€â”€ requirements.txt                 â† Python deps including pytest>=9.0.0
â”‚   â”œâ”€â”€ .env                             â† GITIGNORED. Contains GROQ_API_KEY. Never commit.
â”‚   â”œâ”€â”€ agents\
â”‚   â”‚   â”œâ”€â”€ macro_engineer.py            â† Core LLM planner. Reads: prompt + standards block + RAG + history â†’ OperationGraph JSON
â”‚   â”‚   â””â”€â”€ rag_agent.py                 â† Always-on ChromaDB retrieval, n_results=8, no keyword gate
â”‚   â”œâ”€â”€ standards\
â”‚   â”‚   â””â”€â”€ dimension_resolver.py        â† Deterministic ISO 273/4762/286 lookup tables. All exact numbers come from here.
â”‚   â”‚                                       Call build_standards_context(prompt) â†’ (block, refs) before LLM.
â”‚   â”œâ”€â”€ rag\
â”‚   â”‚   â”œâ”€â”€ vector_store.py              â† ChromaDB wrapper, ONNX embeddings, lazy-init (no model load at startup)
â”‚   â”‚   â”œâ”€â”€ ingestion.py                 â† ingest_pdf / ingest_markdown / ingest_directory / ingest_knowledge_base()
â”‚   â”‚   â””â”€â”€ noop_telemetry.py            â† Suppresses ChromaDB telemetry
â”‚   â”œâ”€â”€ knowledge\                       â† Built-in engineering reference. Auto-ingested at startup if ChromaDB empty.
â”‚   â”‚   â”œâ”€â”€ fastener_reference.md        â† ISO 273 clearance holes + ISO 4762 counterbores, M3â€“M24
â”‚   â”‚   â”œâ”€â”€ design_rules.md              â† Edge distances, wall thickness, corner hole inset rules
â”‚   â”‚   â”œâ”€â”€ standard_fits_tolerances.md  â† ISO 286 fits (H7/h6 etc), GD&T basics
â”‚   â”‚   â””â”€â”€ common_features_library.md   â† Mounting plate, shaft, flange, bracket proportions
â”‚   â”œâ”€â”€ models\
â”‚   â”‚   â””â”€â”€ schemas.py                   â† All Pydantic models. GenerateRequest now has messages[] for history.
â”‚   â”‚                                       OperationGraph has reasoning field (LLM scratchpad, not executed).
â”‚   â””â”€â”€ tests\
â”‚       â”œâ”€â”€ conftest.py                  â† Shared fixtures; backend token loader; requires_backend marker
â”‚       â””â”€â”€ test_security.py             â† 48 tests: auth(6) + auth-success(3) + sanitization(13) + schema(16) + more
â”‚
â””â”€â”€ sw-addin-client\                     â† C# .NET 4.8 SolidWorks Add-in (Codex owns)
    â”œâ”€â”€ SwCopilotAddin.csproj            â† SDK-style, net48, x64, UseWindowsForms=true
    â”œâ”€â”€ Directory.Build.props            â† SolidWorksPath = C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS
    â”œâ”€â”€ Register-DevAddin.ps1            â† Run from elevated PS. Copies interop DLLs â†’ RegAsm â†’ cleans up.
    â”œâ”€â”€ AddinCore\
    â”‚   â”œâ”€â”€ SwAddin.cs                   â† COM entry point: ConnectToSW â†’ AddTaskPane(TaskPaneHost)
    â”‚   â””â”€â”€ AddinInfo.cs                 â† GUID=90562616-2E19-492B-A7B8-9420ABC2CCA2, ProgId="SwCopilotAddin.SwAddin"
    â”œâ”€â”€ UI\
    â”‚   â””â”€â”€ TaskPaneHost.cs              â† WinForms chat panel. Owns _history (List<ConversationMessage>).
    â”‚                                       On submit: passes history to BackendClient â†’ gets AgentResponse â†’
    â”‚                                       shows plan preview dialog â†’ calls OperationExecutor.Execute() â†’
    â”‚                                       appends turn to _history. Routes: OperationGraph â†’ CadCommand â†’ MacroCode.
    â”œâ”€â”€ Client\
    â”‚   â”œâ”€â”€ BackendClient.cs             â† POST /generate with prompt + context + messages[] history.
    â”‚   â”‚                                   Reads token from BackendRuntime.ReadToken().
    â”‚   â”œâ”€â”€ BackendRuntime.cs            â† Auto-starts SwCopilotBackend.exe if backend not running.
    â”‚   â”‚                                   Token file: %LOCALAPPDATA%\SwCopilotAddin\backend.token
    â”‚   â”‚                                   Searches: addinDir\SwCopilotBackend.exe, addinDir\backend\SwCopilotBackend.exe,
    â”‚   â”‚                                             addinDir\backend\SwCopilotBackend\SwCopilotBackend.exe
    â”‚   â”œâ”€â”€ DocumentContextBuilder.cs    â† Reads active doc type, body count, selection from ISldWorks
    â”‚   â”œâ”€â”€ OperationGraphDto.cs         â† C# DTOs for OperationGraph, OperationDto, SketchEntityDto, HolePositionDto.
    â”‚   â”‚                                   Must stay in sync with agent-backend/models/schemas.py.
    â”‚   â””â”€â”€ CadCommandDto.cs             â† Legacy DTO (kept for test compat)
    â””â”€â”€ Execution\
        â”œâ”€â”€ OperationExecutor.cs         â† PRIMARY EXECUTOR. ~850 lines.
        â”‚                                   ValidateGraph() â€” pre-execution rule engine (runs before any COM)
        â”‚                                   Execute() â€” dispatches to 12 op handlers
        â”‚                                   _features dict â€” registers Feature objects by op.Id for cross-op refs
        â”‚                                   SelectTopFaceOfBody() â€” fallback when feature not in _features (cross-request)
        â”œâ”€â”€ CadCommandExecutor.cs        â† Legacy fallback for cad_command path
        â””â”€â”€ MacroExecutor.cs             â† Roslyn fallback (legacy, behind preview + AST denylist)
```

---

## Current Build State

Active repo root: `C:\projects\sw-copilot`.

Latest Codex validation on 2026-05-03:
- Restored missing backend source packages into this repo: `agents/`, `models/`, `rag/`, `standards/`, `knowledge/`, `tests/`.
- Recreated backend venv at `agent-backend\.venv` and installed `agent-backend\requirements.txt`.
- C# build from `sw-addin-client`: 0 warnings, 0 errors.
- Backend tests from `agent-backend`: `47 passed, 1 skipped`; skipped test is live LLM generation when provider quota/rate limit blocks the call.
- Backend import check passed: `OperationGraph.schema_version == "0.2"`.
- C# rollback build on 2026-05-03: `Release-beta3`, 0 warnings, 0 errors.

### Backend (Python) â€” needs uvicorn restart to pick up latest changes

**Start backend:**
```powershell
cd C:\projects\sw-copilot\agent-backend
# Kill anything on 8001 first:
$p = Get-NetTCPConnection -LocalPort 8001 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -First 1
if ($p) { Stop-Process -Id $p -Force; Start-Sleep -Seconds 1 }
.venv\Scripts\python -m uvicorn main:app --host 127.0.0.1 --port 8001
```

**What's working:**
- All routes require `X-Copilot-Token` header (token written to `%LOCALAPPDATA%\SwCopilotAddin\backend.token` at startup)
- `POST /generate` returns `operation_graph` (primary path), falls back to `cad_command`, then `macro_code`
- `GenerateRequest.messages[]` â€” full conversation history passed from add-in, injected as prior turns into LLM
- `standards/dimension_resolver.py` â€” scans prompt for M3â€“M30 fasteners, injects exact ISO dimensions before LLM call
- RAG: 37 chunks in ChromaDB (4 knowledge .md files). Auto-ingested at startup when store is empty.
- LLM system prompt includes engineering reasoning step: LLM derives all dimensions from injected standards before planning
- `OperationGraph.reasoning` field: LLM scratchpad for dimension derivation (not executed, just shows work)
- 48 security tests passing: `cd agent-backend && .venv\Scripts\python -m pytest tests/test_security.py`

**What needs restart to pick up:** All recent Python changes (dimension resolver, rag_agent, macro_engineer, schemas, main).

### C# Add-in â€” BUILDS CLEAN (Release-beta3) âœ…

**Build command (close SolidWorks first â€” it locks the DLL):**
```powershell
cd C:\projects\sw-copilot\sw-addin-client
dotnet build SwCopilotAddin.csproj -c Release -p:Platform=x64 -p:RegisterForComInterop=false `
  -p:OutDir=C:\projects\sw-copilot\sw-addin-client\bin\x64\Release-beta3\net48\
```

**Register (run from elevated PowerShell in sw-addin-client\):**
```powershell
.\Register-DevAddin.ps1
```

**What's implemented and verified:**
- 12 operation types in OperationExecutor: sketch, extrude_boss, extrude_cut, fillet, chamfer, hole_wizard, circular_pattern, linear_pattern, mirror, revolve, delete_feature, noop
- All SolidWorks 2021 COM API signatures verified from DLL introspection (correct arg counts and types)
- Pre-execution rule engine (`ValidateGraph`) catches: zero-area sketches, negative depths, bad angles, missing positions
- `_features` dict: registers created Features by op.Id so later ops can reference earlier ones (within a single Execute call)
- `SelectTopFaceOfBody()` fallback: when feature ID not in `_features` (cross-request refs), scans IPartDoc.GetBodies2() for highest face
- `hole_wizard` plane resolution: standard plane name â†’ select directly; known feature â†’ top face; unknown â†’ body scan
- Conversation history: `TaskPaneHost._history` (List<ConversationMessage>) populated after each response, passed to backend
- Plan preview dialog shown before execution; user can cancel
- Post-execution part report appended after successful `OperationExecutor.Execute()` calls
- Operation graph schema version guard added; non-null versions must equal `"0.2"`
- Undo Last button added to `TaskPaneHost.cs`; `OperationExecutor.RollbackLastExecute()` deletes the features created by the last operation graph.

**Live testing status:**
- âœ… Box creation works (sketch + extrude_boss)
- âš ï¸ Hole wizard follow-up ("add four M5 counterbore holes at the corners") â€” plane resolution fixed, needs re-test after rebuild
- âŒ Not yet tested: fillet, chamfer, circular_pattern, linear_pattern, mirror, revolve, delete_feature

---

## Codex: Immediate Tasks (read these files first, then implement)

### Task C-1: Post-Execution Part Report (Week 1, highest priority) — **Codex DONE 2026-05-03**
**Why:** The validation loop (Week 2) needs to compare what was requested vs. what SW actually built.
**What to build:** New method `ExtractPartReport(IModelDoc2 doc)` in `OperationExecutor.cs` that returns a JSON string.
**Call it** at the end of `Execute()` if no errors, append result to the returned string.

Extract and return:
```json
{
  "body_count": 1,
  "bounding_box": { "x_mm": 50.0, "y_mm": 30.0, "z_mm": 20.0 },
  "mass_g": 234.5,
  "feature_count": 3,
  "features": [
    { "name": "Sketch1", "type": "ProfileFeature", "suppressed": false },
    { "name": "Boss-Extrude1", "type": "Boss", "suppressed": false }
  ]
}
```

SolidWorks API to use:
- `doc.GetBodies2(swSolidBody, true)` â€” on `IPartDoc` cast
- `doc.GetMassProperties()` â€” returns `double[]`: volume(mÂ³), surface(mÂ²), cx,cy,cz(m), Ixx,Ixy,...
  Mass(g) = volume * material_density (assume 7800 kg/mÂ³ for steel if no material set)
- Bounding box: iterate `IBody2.GetBodyBox()` â†’ returns `double[6]` xMin,yMin,zMin,xMax,yMax,zMax
  Convert to mm: `(xMax - xMin) * 1000`
- Feature tree walk: `doc.FirstFeature()` â†’ `f.GetNextFeature()`, collect `f.Name`, `f.GetTypeName2()`, `f.IsSuppressed()`
- JSON serialization: use `Newtonsoft.Json.JsonConvert.SerializeObject(obj, Formatting.None)`

File: `sw-addin-client/Execution/OperationExecutor.cs`

Status:
- Implemented in `OperationExecutor.ExtractPartReport(IModelDoc2 doc)`.
- Successful `Execute()` calls append `Runtime (report): {...}` after final rebuild.
- Report includes body count, combined body bounding box in mm, estimated steel mass in grams, feature count, and feature names/types/suppression state.

---

### Task C-2: Schema Version Field (Week 1) — **Codex DONE 2026-05-03**
**Why:** Defense in depth â€” add-in should refuse to execute graphs from a mismatched backend version.
**What:** Add `public string? SchemaVersion { get; set; }` to `OperationGraphDto` (in `Client/OperationGraphDto.cs`).
In `Execute()`, add at the top: if `graph.SchemaVersion != null && graph.SchemaVersion != "0.2"` â†’ return error string.
**Then write to Handoff Queue** so Claude adds `schema_version: "0.2"` to Python `OperationGraph` schema.

File: `sw-addin-client/Client/OperationGraphDto.cs`

Status:
- Added `OperationGraphDto.SchemaVersion` mapped from JSON `schema_version`.
- `OperationExecutor.Execute()` rejects non-null schema versions that are not `"0.2"`.
- Python `OperationGraph` now includes `schema_version: str = "0.2"` in `agent-backend/models/schemas.py`.

---

### Task C-3: Live Test Suite (Week 1, ongoing)
**Run these prompts in SolidWorks after rebuild + re-register. Record pass/fail here.**

| # | Prompt | Expected | Status |
|---|--------|----------|--------|
| 1 | `create a 50mm wide 30mm deep 20mm tall box` | sketch + extrude_boss, part visible | âœ… |
| 2 | `add four M6 counterbore holes at the corners` | 4 holes on top face of box | âš ï¸ needs re-test |
| 3 | `add a 2mm fillet on all edges` | fillet feature on box | âŒ not tested |
| 4 | `delete everything` | all user features removed | âŒ not tested |
| 5 | `create a 40mm diameter shaft 100mm long` | circle sketch on Front Plane, extrude_boss | âŒ not tested |
| 6 | `add 6 M5 holes on a 60mm bolt circle` | circular_pattern of 1 hole Ã— 6 | âŒ not tested |

After testing, update the Status column and describe any errors in the Handoff Queue.

---

### Task C-4: Rollback Button (Week 2) — **Codex DONE 2026-05-03**
**Why:** Engineer must be able to undo an entire Execute() call.
**What:** In `Execute()`, track which Feature objects were created during this call (not pre-existing).
Add a public `RollbackLastExecute(IModelDoc2 doc)` method that selects and deletes those features.
Expose it in `TaskPaneHost.cs` as a "Undo Last" button in the bottom panel.

Status:
- Implemented `_lastCreatedFeatures` tracking in `OperationExecutor`.
- Added `OperationExecutor.RollbackLastExecute(IModelDoc2? doc = null)`.
- `TaskPaneHost` now owns one persistent `OperationExecutor` and exposes `Undo Last` beside Send.
- Build verified: `Release-beta3`, 0 warnings, 0 errors.

---

## Claude: Immediate Tasks

### Task L-1: Add schema_version to Python schema (after Codex confirms C-2)
File: `agent-backend/models/schemas.py`
Add `schema_version: str = "0.2"` to `OperationGraph`.

### Task L-2: Expand dimension_resolver with ISO 4032 (nuts) and washer data
File: `agent-backend/standards/dimension_resolver.py`

### Task L-3: Write README.md for GitHub
One compelling open-source README: problem statement, architecture diagram (ASCII), install steps, demo prompts, limitation list.

### Task L-4: Backend repair loop
When `OperationExecutor` returns a line starting with `ERROR:` or `RULE VIOLATION`, the add-in should send the error back to `/generate` as a follow-up so the LLM can correct and retry (max 2 attempts). Python side: detect error in conversation history and adjust system prompt for repair.

---

## Architecture Constraints â€” Never Break These

| Constraint | Why |
|---|---|
| `OperationExecutor.Execute()` runs on STA thread | ISldWorks COM is STA-bound; calling from another thread = COM deadlock |
| Backend at `http://127.0.0.1:8001` | IPv4 explicit; "localhost" may resolve to ::1 on some machines |
| All SolidWorks COM dimensions in **metres** | Internal unit. The `Mm(double? value)` helper converts mmâ†’m throughout OperationExecutor |
| `dimension_resolver.py` for all ISO numbers | Vector search cannot be trusted for exact dimensions â€” cosine similarity â‰  lookup table |
| `EmbedInteropTypes=false` on SW interop refs | SW loads these from its own dir; embedding breaks COM type identity |
| `response_format={"type":"json_object"}` on Groq | Enforces JSON output; retry loop corrects schema failures |
| ChromaDB holds explanatory text only | Exact numbers â†’ Python dict in dimension_resolver. Text â†’ ChromaDB. |
| `_features` dict is per-Execute-call | Cross-request refs (e.g., "f1" from previous message) fall back to `SelectTopFaceOfBody()` |

---

## Verified SolidWorks 2021 COM API Signatures

These were introspected from the actual DLL. Do not change arg counts.

```csharp
// Sketch
sketchMgr.InsertSketch(true)                          // call twice: open, then close
sketchMgr.CreateCornerRectangle(x1,y1,0, x2,y2,0)    // metres
sketchMgr.CreateCircleByRadius(cx,cy,0, radius)        // metres
sketchMgr.CreateLine(x1,y1,0, x2,y2,0)

// Extrude
featMgr.FeatureExtrusion2(true,false,false, endCond,0, depth,0, false,false,false,false, 0,0, false,false,false,false, true,true,true, 0,0.0,false)
featMgr.FeatureCut3(true,false,false, endCond,swEndCondBlind, depth,0, false,false,false,false, 0,0, false,false,false,false, false,true,true,true,true,false, 0,0.0,false)

// Fillet â€” returns object, must cast to Feature
(Feature)featMgr.FeatureFillet(Options, R1, Ftyp, OverflowType, Radii_obj[], SetBackDist_obj[], PointRadius_obj[])
// Chamfer â€” returns object, must cast to Feature
(Feature)featMgr.InsertFeatureChamfer(Options, ChamferType, Width, Angle, OtherDist, VD1, VD2, VD3)

// Patterns
featMgr.FeatureCircularPattern3(Number, Spacing, FlipDirection, DName, GeometryPattern, EqualSpacing)   // 6 params
featMgr.FeatureLinearPattern3(Num1,Spacing1, Num2,Spacing2, FlipDir1,FlipDir2, DName1,DName2, GeomPat, VaryInstance)  // 10 params
featMgr.InsertMirrorFeature2(BMirrorBody, BGeometryPattern, BMerge, BKnit, ScopeOptions)   // 5 params

// Revolve â€” 20 params
featMgr.FeatureRevolve2(SingleDir, IsSolid, IsThin, IsCut, ReverseDir, BothDirUpToSame,
  Dir1Type, Dir2Type, Dir1Angle, Dir2Angle, OffsetReverse1, OffsetReverse2,
  OffsetDistance1, OffsetDistance2, ThinType, ThinThickness1, ThinThickness2,
  Merge, UseFeatScope, UseAutoSelect)

// GetBodies2 is on IPartDoc, NOT IModelDoc2
IPartDoc part = doc as IPartDoc;
object[] bodies = part?.GetBodies2((int)swBodyType_e.swSolidBody, true) as object[];
```

---

## Security Model

- Token: `%LOCALAPPDATA%\SwCopilotAddin\backend.token` â€” 64-char hex, regenerated every uvicorn startup
- All FastAPI routes protected by `X-Copilot-Token` header (timing-safe `secrets.compare_digest`)
- Context strings sanitized before LLM: newlines, backticks, injection keywords â†’ `[REDACTED]`, truncated to 1024 chars
- Pre-execution rule engine: geometric impossibilities refused before COM
- MacroExecutor (Roslyn) is legacy only â€” always behind preview dialog + AST denylist â€” never primary path

---

## Handoff Queue
*(Both agents check this section at the start of every session. Cross it off when done.)*

- [x] **[Claude â†’ Codex]** Post-execution extractor (Task C-1): after Execute() completes with no errors, call `ExtractPartReport(doc)` and append JSON to the returned result string. Feed it back through the chat as `Runtime (report): {...}`. This enables the validation loop in Week 2.

- [x] **[Claude â†’ Codex]** Schema version (Task C-2): add `SchemaVersion` to `OperationGraphDto`. Matching `schema_version: str = "0.2"` is present in `agent-backend/models/schemas.py`.

- [ ] **[Codex â†’ Claude]** After each live test (Task C-3), write results to the test table above. If any operation type fails with a specific COM error, paste it in this queue and Claude will fix the Python planner to avoid generating that pattern.

- [x] **[Codex â†’ Claude]** `Rollback` button is added to TaskPaneHost (Task C-4). Backend can now add a future `rollback_id`/audit field without blocking C# execution.

