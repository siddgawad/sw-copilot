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
7. Post-execution validation â€” backend `/validate` compares requested OperationGraph to C# PartReport

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
â”‚       â””â”€â”€ test_security.py             â† 54 tests: auth + auth-success + sanitization + schema regression
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
- Backend tests from `agent-backend`: `129 passed, 9 skipped`; skipped tests are backend-required/live-service checks when uvicorn or provider quota is unavailable.
- Backend import check passed: `OperationGraph.schema_version == "0.2"`.
- C# rollback build on 2026-05-03: `Release-beta3`, 0 warnings, 0 errors.
- C# repair-loop build on 2026-05-03: `Release-beta4`, 0 warnings, 0 errors.
- Beta package build on 2026-05-03 succeeded: `artifacts\sw-copilot-beta.zip` (112,088,812 bytes). SHA-256 `5F5D4BE93065CF988F0FBA020F892CB0090A84444F05F0471FA6F10433668967`. Packaged backend `/version` smoke check passed on port 8002 with `vector_docs=37`; packaged `/validate` smoke passed with `passed=true`.
- Sanitizer hardening on 2026-05-03: C# strips full paths to filenames before context upload; C# and Python both remove newlines/backticks/control chars and redact injection markers. Backend sanitizer tests: `19 passed`; full security suite: `53 passed, 1 skipped`; smoke test: `10 passed, 1 skipped, 0 failed` (LLM rate-limit skip).
- Validation/context-budget hotfix on 2026-05-03: sketch-only/noop/delete-only graphs no longer fail validation for `body_count=0`; TaskPaneHost and BackendClient now cap history to 8 messages / 3000 chars and store compact runtime summaries instead of full PartReport feature trees; backend trims history defensively, caps RAG to 2 chunks / 2500 chars, lowers Groq max output tokens to 1536, and retries short 429 rate-limit responses twice. Backend tests: `139 passed`. C# build: `Release-beta5`, 0 warnings, 0 errors. New side-by-side beta package: `artifacts\sw-copilot-beta5.zip` (112,091,851 bytes). SHA-256 `A6A19E10AB9AFB33B14F473D00EBFD77B1E4FE65BC75C191C7FA6BEF5169A258`; packaged `/version` smoke passed on port 8002 with `vector_docs=37`.
- Red-team architecture hotfix on 2026-05-03: multiple holes on a cylinder/round top without PCD or explicit positions now fast-paths to clarification before Groq; normal system prompt replaced with compact production prompt to reduce TPM; `OperationExecutor.ValidateGraph()` now rejects overlapping hole positions before COM; `TaskPaneHost` no longer auto-repairs deterministic `RULE VIOLATION` or `ERROR: Hole cut failed` responses. Backend tests: `141 passed`. C# build: `Release-beta6`, 0 warnings, 0 errors. New package: `artifacts\sw-copilot-beta6.zip` (112,094,322 bytes). SHA-256 `31B84351CEEB897DD9F5E020EE9E2C3C9FDA0C4A8A0B0394531647FF1DA6BFF7`; packaged `/version` smoke passed on port 8003 with `vector_docs=37`.
- AI Factory baseline on 2026-05-03: external command-center created at `C:\AI-Factory`. SW Copilot remains at `C:\projects\sw-copilot` and is registered in `C:\AI-Factory\control\.ai\state\projects.json`; no repo move was performed. Project-level Claude agents added under `.claude\agents\`; project Codex default added under `.codex\config.toml`. AI Factory evidence scripts verified: git snapshot generated, deterministic backend subset `132 passed`, C# build `0 warnings, 0 errors`, latest status report generated.

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
- `POST /validate` compares an OperationGraph against the C# PartReport and returns discrepancies for bbox/body/features
- `GenerateRequest.messages[]` â€” full conversation history passed from add-in, injected as prior turns into LLM
- `standards/dimension_resolver.py` â€” scans prompt for M3â€“M30 fasteners, injects exact ISO dimensions before LLM call
- RAG: 37 chunks in ChromaDB (4 knowledge .md files). Auto-ingested at startup when store is empty.
- LLM system prompt includes engineering reasoning step: LLM derives all dimensions from injected standards before planning
- `OperationGraph.reasoning` field: LLM scratchpad for dimension derivation (not executed, just shows work)
- 54 security tests passing/skipping as expected: `cd agent-backend && .venv\Scripts\python -m pytest tests/test_security.py`

**What needs restart to pick up:** All recent Python changes (dimension resolver, rag_agent, macro_engineer, schemas, main).

**Packaged backend:**
- `agent-backend/run_backend.py` is the PyInstaller entrypoint. It starts uvicorn for `main:app`.
- `agent-backend/sw_copilot_backend.spec` must point at `run_backend.py`, not `main.py`.
- Build-only dependency is in `agent-backend/requirements-build.txt`.

### C# Add-in â€” BUILDS CLEAN (Release-beta4) âœ…

**Build command (close SolidWorks first â€” it locks the DLL):**
```powershell
cd C:\projects\sw-copilot\sw-addin-client
dotnet build SwCopilotAddin.csproj -c Release -p:Platform=x64 -p:RegisterForComInterop=false `
  -p:OutDir=C:\projects\sw-copilot\sw-addin-client\bin\x64\Release-beta4\net48\
```

**Register (run from elevated PowerShell in sw-addin-client\):**
```powershell
.\Register-DevAddin.ps1
```

**Build shareable beta package:**
```powershell
cd C:\projects\sw-copilot
agent-backend\.venv\Scripts\python.exe -m pip install -r agent-backend\requirements-build.txt
.\scripts\Build-BetaPackage.ps1
```
Output: `artifacts\sw-copilot-beta.zip`.

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
- TaskPaneHost now sends the part report to backend `/validate` and appends validation pass/warning/error output to chat
- Operation graph schema version guard added; non-null versions must equal `"0.2"`
- Undo Last button added to `TaskPaneHost.cs`; `OperationExecutor.RollbackLastExecute()` deletes the features created by the last operation graph.
- Release package script added: `scripts\Build-BetaPackage.ps1`.

**Live testing status:**
- âœ… Box creation works (sketch + extrude_boss)
- âš ï¸ Hole wizard follow-up ("add four M5 counterbore holes at the corners") â€” plane resolution fixed, needs re-test after rebuild
- âœ… Sketch-only request behavior fixed in code/tests: `make a circle 30mm` should validate as a sketch with no solid body, not as a failed extrude. Needs live SolidWorks re-test on beta5.
- âš ï¸ Groq TPM spike after follow-up commands mitigated: C# no longer sends full runtime feature-tree reports in history; backend RAG/history/output budgets reduced. For global launch, this still requires a real hosted inference/billing strategy rather than one shared Groq on-demand key.
- âœ… Cylinder top-hole red-team case fixed in code/tests: after `make a circle 30mm extrude it 30mm`, `add four M6 counterbore holes at the top` should ask for PCD/positions instead of guessing corner insets, failing COM, and burning repair calls. Needs live SolidWorks re-test on beta6.
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

### Task L-1: schema_version on Python OperationGraph — **Claude DONE 2026-05-03**
- Added `schema_version: str = "0.2"` to `OperationGraph` in `agent-backend/models/schemas.py:291`. Codex's C-2 guard accepts this value.

### Task L-2: ISO 4032 nuts + ISO 7089 washers in dimension_resolver — **Claude DONE 2026-05-04**
- Added `HexNut` and `Washer` dataclasses, `_HEX_NUT` (M3–M30) and `_WASHER` (M3–M30) tables, and `resolve_hex_nut()` / `resolve_washer()` to `agent-backend/standards/dimension_resolver.py`.
- `resolve_all()` and `build_standards_context()` now surface nut WAF/height and washer OD/thickness so the LLM can reason about nut/washer stack-up height.

### Task L-3: GitHub README — **Claude DONE 2026-05-03**
- `README.md` at repo root: problem statement, ASCII architecture diagram, supported ops table, demo prompts, ISO standards table, setup, security, limitations.

### Task L-4: Backend repair loop — **Claude DONE 2026-05-04**
- `_has_execution_error()` scans the most recent assistant turn for `ERROR:` / `RULE VIOLATION`.
- When triggered, `_REPAIR_ADDENDUM` is appended to the system prompt instructing the LLM to inspect the prior error and emit a corrected graph.
- File: `agent-backend/agents/macro_engineer.py`.
- C# side still owes the auto-resend (send executor error back to `/generate` as a follow-up, max 2 attempts) — currently the repair-mode prompt only fires if the user manually re-prompts after a failed turn. **Codex: please wire this in `TaskPaneHost.SubmitAsync` once you have appetite.**

### Task L-5: Resolver + repair-loop regression tests — **Claude DONE 2026-05-04**
- `agent-backend/tests/test_dimension_resolver.py`: 60 spot checks against ISO 273, 4762, 4032, 7089, 724/965 plus repair-mode detector. Run with `pytest tests/test_dimension_resolver.py`.
- Full suite: `105 passed, 9 skipped` (skipped = backend-required tests when uvicorn is not running).

### Task L-6: Post-execution validation agent (pipeline step 7) — **Claude DONE 2026-05-04**
- `agent-backend/agents/validation_agent.py`: `validate(graph, report, tolerance_mm)` compares the requested `OperationGraph` against Codex's `PartReport` and emits a `ValidationReport` with categorised discrepancies (`bounding_box`, `body_count`, `feature_count`, `suppressed_feature`, etc.).
- Models added to `models/schemas.py`: `BoundingBox`, `PartFeatureInfo`, `PartReport`, `Discrepancy`, `ValidationReport`, `ValidateRequest`.
- New endpoint: `POST /validate` (token-gated). Body: `{"operation_graph": ..., "part_report": ..., "tolerance_mm": 1.0}` → `ValidationReport`.
- Coverage today: bounding-box derivation for single-extrude graphs (Top/Front/Right Plane), body-count sanity, feature-count lower bound, suppressed-feature detection. Multi-extrude graphs safely skip the bbox check rather than emit false positives.
- Tests: `agent-backend/tests/test_validation_agent.py` — 17 cases including a tolerance sweep. Full suite now `122 passed, 9 skipped`.
- **Codex integration**: `TaskPaneHost` now POSTs `{operation_graph, part_report}` to `/validate` after successful execution and surfaces validation pass/warning/error output in chat.

### Task L-7: Prompt/token-budget hardening — **Codex DONE 2026-05-03**
- Finished Claude's interrupted refactor in `agent-backend/agents/macro_engineer.py`: `build_user_message()` and `build_system_prompt()` are now pure functions so prompt construction can be tested without calling Groq.
- `agent-backend/agents/rag_agent.py`: skips RAG for simple primitive prompts, caps retrieval to 4 chunks, and caps injected RAG text to 6000 characters.
- `agent-backend/standards/dimension_resolver.py`: caps deterministic standards context to the first 3 fastener sizes in long prompts, preserving exact ISO data while preventing BOM-like prompts from blowing the context budget.
- Added `agent-backend/tests/test_prompt_budget.py` covering simple-prompt budget, fastener standards injection, repair addendum triggering, stale-error behavior, RAG relevance gating, and RAG output caps.
- Validation: full backend suite `129 passed, 9 skipped`.

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
- Context strings sanitized before LLM: newlines, backticks, control chars, injection markers -> `[REDACTED]`, truncated to 1024 chars. C# sends only the file name, not the full local path.
- Pre-execution rule engine: geometric impossibilities refused before COM
- MacroExecutor (Roslyn) is legacy only â€” always behind preview dialog + AST denylist â€” never primary path

---

## Handoff Queue
*(Both agents check this section at the start of every session. Cross it off when done.)*

- [x] **[Claude â†’ Codex]** Post-execution extractor (Task C-1): after Execute() completes with no errors, call `ExtractPartReport(doc)` and append JSON to the returned result string. Feed it back through the chat as `Runtime (report): {...}`. This enables the validation loop in Week 2.

- [x] **[Claude â†’ Codex]** Schema version (Task C-2): add `SchemaVersion` to `OperationGraphDto`. Matching `schema_version: str = "0.2"` is present in `agent-backend/models/schemas.py`.

- [ ] **[Codex â†’ Claude]** After each live test (Task C-3), write results to the test table above. If any operation type fails with a specific COM error, paste it in this queue and Claude will fix the Python planner to avoid generating that pattern.

- [x] **[Codex â†’ Claude]** `Rollback` button is added to TaskPaneHost (Task C-4). Backend can now add a future `rollback_id`/audit field without blocking C# execution.

- [x] **[Codex â†’ Claude]** Packaging pivot: PyInstaller now uses `agent-backend/run_backend.py` so the EXE actually starts uvicorn. If Claude changes backend startup behavior, keep `run_backend.py` and `sw_copilot_backend.spec` in sync. `scripts\Build-BetaPackage.ps1` produces `artifacts\sw-copilot-beta.zip`.

- [x] **[Claude â†’ Codex]** Repair loop is wired Python-side (Task L-4): C# auto-resend is now wired in `TaskPaneHost.SubmitAsync` through `ExecuteOperationGraphWithRepairAsync`. It detects `ERROR:` / `RULE VIOLATION`, appends the failed graph + runtime error to temporary assistant history, and calls `/generate` again for up to 2 automatic repair attempts. Every repaired graph still requires preview confirmation before execution. Verified: C# `Release-beta4` build clean, backend pytest `122 passed, 9 skipped`.

- [x] **[Claude â†’ Codex]** Validation endpoint shipped (Task L-6): `POST /validate` accepts `{operation_graph, part_report, tolerance_mm}` and returns a `ValidationReport`. C# integration is wired in `BackendClient.ValidateOperationAsync()` + `TaskPaneHost.ValidateExecutionResultAsync()` and surfaces validation output in chat.

- [x] **[Codex â†’ Claude]** Backend prompt/token-budget hardening: completed while Claude was unavailable. Simple primitive prompts now skip RAG, injected RAG is capped, deterministic standards context is capped to 3 fastener sizes, prompt builders are testable without Groq, and `tests/test_prompt_budget.py` locks the behavior. Full backend suite: `129 passed, 9 skipped`.

---

## Current Work Split - 2026-05-03

**Codex owns now:**
- `sw-addin-client/UI/TaskPaneHost.cs`: automatic repair retry loop, legacy Roslyn fallback blocked by default, C# build/package validation.
- `scripts/Build-BetaPackage.ps1`: rebuild `artifacts/sw-copilot-beta.zip` after validation.

**Claude owns next if available:**
- `agent-backend/` only: prompt/token-budget hardening, backend tests, and documentation updates for the next prototype.
- Do not touch C# while Codex is validating beta4.

**Prompt to paste into Claude Code:**
```text
Read C:\projects\sw-copilot\CLAUDE.md first. Own agent-backend/ only. Codex is handling C# beta4 repair-loop validation and packaging, so do not edit sw-addin-client/.

Your task: harden backend prompt/token budget for the next testable prototype. Inspect agents/macro_engineer.py, agents/rag_agent.py, standards/dimension_resolver.py, and tests/. Reduce token/character usage for simple primitive prompts without weakening deterministic standards grounding. Keep repair mode working when the latest assistant history contains ERROR: or RULE VIOLATION. Add no-live-LLM regression tests proving: (1) repair addendum triggers from assistant error history, (2) simple prompts do not include excessive RAG/API context, (3) standards context still appears for fastener prompts. Run pytest. Update CLAUDE.md with exact files changed and results. Commit your changes.
```
