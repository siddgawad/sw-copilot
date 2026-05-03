# SW Copilot — Project State (Single Source of Truth)

**Both Claude and Codex must read this entire file before touching any code.**
Both agents have full filesystem access. Read the actual files — don't guess at state.
Update the relevant section whenever you complete, break, or discover something new.

---

## What This Is

A standards-grounded AI add-in for SolidWorks 2021.
Natural language → LLM operation planner → validated JSON graph → deterministic C# COM executor.

The LLM is a compiler frontend. The C# executor is the backend. ISO standards data is the type system.
This is NOT "make LLM understand CAD." Reliability comes from determinism at every layer after the LLM.

**Execution pipeline (in order, never skip a layer):**
1. `standards/dimension_resolver.py` — exact ISO 273/4762 numbers injected before LLM sees the prompt
2. `rag/` (ChromaDB) — explanatory engineering text retrieved and injected (semantic, NOT for exact numbers)
3. `agents/macro_engineer.py` — LLM emits OperationGraph JSON with a reasoning scratchpad
4. Pydantic validation (Python) + DTO validation (C#) — schema enforced before any execution
5. `OperationExecutor.ValidateGraph()` — geometric rule engine refuses impossibilities before COM
6. `OperationExecutor.Execute()` — deterministic SolidWorks COM calls, 12 operation types
7. Post-execution validation — TODO Week 2 (Codex task)

---

## How the Two Agents Coordinate

- **Claude** owns the Python backend (`agent-backend/`), schemas, RAG, standards data, tests, docs.
- **Codex** owns the C# add-in (`sw-addin-client/`), COM execution, UI, packaging, live SW testing.
- **Shared boundary**: `models/schemas.py` (Python) ↔ `Client/OperationGraphDto.cs` (C#) must stay in sync.
  When either agent changes the operation schema, they write to the Handoff Queue below and the other agent mirrors it.
- **Communication**: write to Handoff Queue in this file. The other agent reads CLAUDE.md before every session.
- **Git**: both agents commit to the same repo at `C:\Users\theof\` (root). Commit after every meaningful change.

---

## Repository Layout — Read These Files Directly

```
C:\Users\theof\                          ← git repo root
├── CLAUDE.md                            ← THIS FILE. Both agents update it.
├── .gitignore
│
├── agent-backend\                       ← Python FastAPI backend (Claude owns)
│   ├── main.py                          ← FastAPI app: /generate /ingest /health /version
│   ├── config.py                        ← Settings from .env: GROQ_API_KEY, groq_model, etc.
│   ├── requirements.txt                 ← Python deps including pytest>=9.0.0
│   ├── .env                             ← GITIGNORED. Contains GROQ_API_KEY. Never commit.
│   ├── agents\
│   │   ├── macro_engineer.py            ← Core LLM planner. Reads: prompt + standards block + RAG + history → OperationGraph JSON
│   │   └── rag_agent.py                 ← Always-on ChromaDB retrieval, n_results=8, no keyword gate
│   ├── standards\
│   │   └── dimension_resolver.py        ← Deterministic ISO 273/4762/286 lookup tables. All exact numbers come from here.
│   │                                       Call build_standards_context(prompt) → (block, refs) before LLM.
│   ├── rag\
│   │   ├── vector_store.py              ← ChromaDB wrapper, ONNX embeddings, lazy-init (no model load at startup)
│   │   ├── ingestion.py                 ← ingest_pdf / ingest_markdown / ingest_directory / ingest_knowledge_base()
│   │   └── noop_telemetry.py            ← Suppresses ChromaDB telemetry
│   ├── knowledge\                       ← Built-in engineering reference. Auto-ingested at startup if ChromaDB empty.
│   │   ├── fastener_reference.md        ← ISO 273 clearance holes + ISO 4762 counterbores, M3–M24
│   │   ├── design_rules.md              ← Edge distances, wall thickness, corner hole inset rules
│   │   ├── standard_fits_tolerances.md  ← ISO 286 fits (H7/h6 etc), GD&T basics
│   │   └── common_features_library.md   ← Mounting plate, shaft, flange, bracket proportions
│   ├── models\
│   │   └── schemas.py                   ← All Pydantic models. GenerateRequest now has messages[] for history.
│   │                                       OperationGraph has reasoning field (LLM scratchpad, not executed).
│   └── tests\
│       ├── conftest.py                  ← Shared fixtures; backend token loader; requires_backend marker
│       └── test_security.py             ← 48 tests: auth(6) + auth-success(3) + sanitization(13) + schema(16) + more
│
└── sw-addin-client\                     ← C# .NET 4.8 SolidWorks Add-in (Codex owns)
    ├── SwCopilotAddin.csproj            ← SDK-style, net48, x64, UseWindowsForms=true
    ├── Directory.Build.props            ← SolidWorksPath = C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS
    ├── Register-DevAddin.ps1            ← Run from elevated PS. Copies interop DLLs → RegAsm → cleans up.
    ├── AddinCore\
    │   ├── SwAddin.cs                   ← COM entry point: ConnectToSW → AddTaskPane(TaskPaneHost)
    │   └── AddinInfo.cs                 ← GUID=90562616-2E19-492B-A7B8-9420ABC2CCA2, ProgId="SwCopilotAddin.SwAddin"
    ├── UI\
    │   └── TaskPaneHost.cs              ← WinForms chat panel. Owns _history (List<ConversationMessage>).
    │                                       On submit: passes history to BackendClient → gets AgentResponse →
    │                                       shows plan preview dialog → calls OperationExecutor.Execute() →
    │                                       appends turn to _history. Routes: OperationGraph → CadCommand → MacroCode.
    ├── Client\
    │   ├── BackendClient.cs             ← POST /generate with prompt + context + messages[] history.
    │   │                                   Reads token from BackendRuntime.ReadToken().
    │   ├── BackendRuntime.cs            ← Auto-starts SwCopilotBackend.exe if backend not running.
    │   │                                   Token file: %LOCALAPPDATA%\SwCopilotAddin\backend.token
    │   │                                   Searches: addinDir\SwCopilotBackend.exe, addinDir\backend\SwCopilotBackend.exe,
    │   │                                             addinDir\backend\SwCopilotBackend\SwCopilotBackend.exe
    │   ├── DocumentContextBuilder.cs    ← Reads active doc type, body count, selection from ISldWorks
    │   ├── OperationGraphDto.cs         ← C# DTOs for OperationGraph, OperationDto, SketchEntityDto, HolePositionDto.
    │   │                                   Must stay in sync with agent-backend/models/schemas.py.
    │   └── CadCommandDto.cs             ← Legacy DTO (kept for test compat)
    └── Execution\
        ├── OperationExecutor.cs         ← PRIMARY EXECUTOR. ~850 lines.
        │                                   ValidateGraph() — pre-execution rule engine (runs before any COM)
        │                                   Execute() — dispatches to 12 op handlers
        │                                   _features dict — registers Feature objects by op.Id for cross-op refs
        │                                   SelectTopFaceOfBody() — fallback when feature not in _features (cross-request)
        ├── CadCommandExecutor.cs        ← Legacy fallback for cad_command path
        └── MacroExecutor.cs             ← Roslyn fallback (legacy, behind preview + AST denylist)
```

---

## Current Build State

### Backend (Python) — needs uvicorn restart to pick up latest changes

**Start backend:**
```powershell
cd C:\Users\theof\agent-backend
# Kill anything on 8001 first:
$p = Get-NetTCPConnection -LocalPort 8001 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -First 1
if ($p) { Stop-Process -Id $p -Force; Start-Sleep -Seconds 1 }
.venv\Scripts\python -m uvicorn main:app --host 127.0.0.1 --port 8001
```

**What's working:**
- All routes require `X-Copilot-Token` header (token written to `%LOCALAPPDATA%\SwCopilotAddin\backend.token` at startup)
- `POST /generate` returns `operation_graph` (primary path), falls back to `cad_command`, then `macro_code`
- `GenerateRequest.messages[]` — full conversation history passed from add-in, injected as prior turns into LLM
- `standards/dimension_resolver.py` — scans prompt for M3–M30 fasteners, injects exact ISO dimensions before LLM call
- RAG: 37 chunks in ChromaDB (4 knowledge .md files). Auto-ingested at startup when store is empty.
- LLM system prompt includes engineering reasoning step: LLM derives all dimensions from injected standards before planning
- `OperationGraph.reasoning` field: LLM scratchpad for dimension derivation (not executed, just shows work)
- 48 security tests passing: `cd agent-backend && .venv\Scripts\python -m pytest tests/test_security.py`

**What needs restart to pick up:** All recent Python changes (dimension resolver, rag_agent, macro_engineer, schemas, main).

### C# Add-in — BUILDS CLEAN (Release-beta2) ✅

**Build command (close SolidWorks first — it locks the DLL):**
```powershell
cd C:\Users\theof\sw-addin-client
dotnet build SwCopilotAddin.csproj -c Release -p:Platform=x64 -p:RegisterForComInterop=false `
  -p:OutDir=C:\Users\theof\sw-addin-client\bin\x64\Release-beta2\net48\
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
- `hole_wizard` plane resolution: standard plane name → select directly; known feature → top face; unknown → body scan
- Conversation history: `TaskPaneHost._history` (List<ConversationMessage>) populated after each response, passed to backend
- Plan preview dialog shown before execution; user can cancel

**Live testing status:**
- ✅ Box creation works (sketch + extrude_boss)
- ⚠️ Hole wizard follow-up ("add four M5 counterbore holes at the corners") — plane resolution fixed, needs re-test after rebuild
- ❌ Not yet tested: fillet, chamfer, circular_pattern, linear_pattern, mirror, revolve, delete_feature

---

## Codex: Immediate Tasks (read these files first, then implement)

### Task C-1: Post-Execution Part Report (Week 1, highest priority)
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
- `doc.GetBodies2(swSolidBody, true)` — on `IPartDoc` cast
- `doc.GetMassProperties()` — returns `double[]`: volume(m³), surface(m²), cx,cy,cz(m), Ixx,Ixy,...
  Mass(g) = volume * material_density (assume 7800 kg/m³ for steel if no material set)
- Bounding box: iterate `IBody2.GetBodyBox()` → returns `double[6]` xMin,yMin,zMin,xMax,yMax,zMax
  Convert to mm: `(xMax - xMin) * 1000`
- Feature tree walk: `doc.FirstFeature()` → `f.GetNextFeature()`, collect `f.Name`, `f.GetTypeName2()`, `f.IsSuppressed()`
- JSON serialization: use `Newtonsoft.Json.JsonConvert.SerializeObject(obj, Formatting.None)`

File: `sw-addin-client/Execution/OperationExecutor.cs`

---

### Task C-2: Schema Version Field (Week 1)
**Why:** Defense in depth — add-in should refuse to execute graphs from a mismatched backend version.
**What:** Add `public string? SchemaVersion { get; set; }` to `OperationGraphDto` (in `Client/OperationGraphDto.cs`).
In `Execute()`, add at the top: if `graph.SchemaVersion != null && graph.SchemaVersion != "0.2"` → return error string.
**Then write to Handoff Queue** so Claude adds `schema_version: "0.2"` to Python `OperationGraph` schema.

File: `sw-addin-client/Client/OperationGraphDto.cs`

---

### Task C-3: Live Test Suite (Week 1, ongoing)
**Run these prompts in SolidWorks after rebuild + re-register. Record pass/fail here.**

| # | Prompt | Expected | Status |
|---|--------|----------|--------|
| 1 | `create a 50mm wide 30mm deep 20mm tall box` | sketch + extrude_boss, part visible | ✅ |
| 2 | `add four M6 counterbore holes at the corners` | 4 holes on top face of box | ⚠️ needs re-test |
| 3 | `add a 2mm fillet on all edges` | fillet feature on box | ❌ not tested |
| 4 | `delete everything` | all user features removed | ❌ not tested |
| 5 | `create a 40mm diameter shaft 100mm long` | circle sketch on Front Plane, extrude_boss | ❌ not tested |
| 6 | `add 6 M5 holes on a 60mm bolt circle` | circular_pattern of 1 hole × 6 | ❌ not tested |

After testing, update the Status column and describe any errors in the Handoff Queue.

---

### Task C-4: Rollback Button (Week 2)
**Why:** Engineer must be able to undo an entire Execute() call.
**What:** In `Execute()`, track which Feature objects were created during this call (not pre-existing).
Add a public `RollbackLastExecute(IModelDoc2 doc)` method that selects and deletes those features.
Expose it in `TaskPaneHost.cs` as a "Undo Last" button in the bottom panel.

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

## Architecture Constraints — Never Break These

| Constraint | Why |
|---|---|
| `OperationExecutor.Execute()` runs on STA thread | ISldWorks COM is STA-bound; calling from another thread = COM deadlock |
| Backend at `http://127.0.0.1:8001` | IPv4 explicit; "localhost" may resolve to ::1 on some machines |
| All SolidWorks COM dimensions in **metres** | Internal unit. The `Mm(double? value)` helper converts mm→m throughout OperationExecutor |
| `dimension_resolver.py` for all ISO numbers | Vector search cannot be trusted for exact dimensions — cosine similarity ≠ lookup table |
| `EmbedInteropTypes=false` on SW interop refs | SW loads these from its own dir; embedding breaks COM type identity |
| `response_format={"type":"json_object"}` on Groq | Enforces JSON output; retry loop corrects schema failures |
| ChromaDB holds explanatory text only | Exact numbers → Python dict in dimension_resolver. Text → ChromaDB. |
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

// Fillet — returns object, must cast to Feature
(Feature)featMgr.FeatureFillet(Options, R1, Ftyp, OverflowType, Radii_obj[], SetBackDist_obj[], PointRadius_obj[])
// Chamfer — returns object, must cast to Feature
(Feature)featMgr.InsertFeatureChamfer(Options, ChamferType, Width, Angle, OtherDist, VD1, VD2, VD3)

// Patterns
featMgr.FeatureCircularPattern3(Number, Spacing, FlipDirection, DName, GeometryPattern, EqualSpacing)   // 6 params
featMgr.FeatureLinearPattern3(Num1,Spacing1, Num2,Spacing2, FlipDir1,FlipDir2, DName1,DName2, GeomPat, VaryInstance)  // 10 params
featMgr.InsertMirrorFeature2(BMirrorBody, BGeometryPattern, BMerge, BKnit, ScopeOptions)   // 5 params

// Revolve — 20 params
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

- Token: `%LOCALAPPDATA%\SwCopilotAddin\backend.token` — 64-char hex, regenerated every uvicorn startup
- All FastAPI routes protected by `X-Copilot-Token` header (timing-safe `secrets.compare_digest`)
- Context strings sanitized before LLM: newlines, backticks, injection keywords → `[REDACTED]`, truncated to 1024 chars
- Pre-execution rule engine: geometric impossibilities refused before COM
- MacroExecutor (Roslyn) is legacy only — always behind preview dialog + AST denylist — never primary path

---

## Handoff Queue
*(Both agents check this section at the start of every session. Cross it off when done.)*

- [ ] **[Claude → Codex]** Post-execution extractor (Task C-1): after Execute() completes with no errors, call `ExtractPartReport(doc)` and append JSON to the returned result string. Feed it back through the chat as `Runtime (report): {...}`. This enables the validation loop in Week 2.

- [ ] **[Claude → Codex]** Schema version (Task C-2): add `SchemaVersion` to `OperationGraphDto`. When Codex confirms the DTO field name, Claude will add `schema_version: str = "0.2"` to `OperationGraph` in `models/schemas.py`.

- [ ] **[Codex → Claude]** After each live test (Task C-3), write results to the test table above. If any operation type fails with a specific COM error, paste it in this queue and Claude will fix the Python planner to avoid generating that pattern.

- [ ] **[Codex → Claude]** When the `Rollback` button is added to TaskPaneHost (Task C-4), let Claude know so the backend can record a `rollback_id` in the response for audit logging.
