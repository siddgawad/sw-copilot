# SW Copilot — Project State (Single Source of Truth)

**Every agent reads this file before touching any code.** Update the
**Handoff Queue** whenever you complete, break, or discover something new.

For settled task history see `docs/CHANGELOG.md`.
For SW COM signatures see `docs/SOLIDWORKS_API_REFERENCE.md`.
For agent routing and the local-agent task-card contract see `docs/AGENT_PLAYBOOK.md`.

---

## What This Is

A standards-grounded AI add-in for SolidWorks 2021. Natural language ->
LLM operation planner -> validated JSON graph -> deterministic C# COM
executor. The LLM is a compiler frontend; reliability comes from
determinism at every layer after it.

**Execution pipeline (in order, never skip a layer):**

1. `standards/dimension_resolver.py` — exact ISO 273/4762/4032/7089
   numbers injected before the LLM sees the prompt.
2. `rag/` (ChromaDB) — explanatory engineering text, semantic only,
   never for exact numbers.
3. `agents/macro_engineer.py` — LLM emits OperationGraph JSON.
4. Pydantic validation (Python) + DTO validation (C#).
5. `OperationExecutor.ValidateGraph()` — geometric rule engine refuses
   impossibilities before COM.
6. `OperationExecutor.Execute()` — deterministic SW COM, 12 op types.
7. `POST /validate` — backend compares requested graph to C# PartReport.

---

## Ownership

- **Claude (Opus 4.7)** owns `agent-backend/`: schemas, RAG, standards
  data, validation agent, tests, docs.
- **Codex (GPT-5-Codex)** owns `sw-addin-client/`: COM execution, UI,
  packaging, live SW testing.
- **Qwen2.5-Coder-7B (local)** picks up isolated, single-file, mechanical
  work assigned via task cards. See `docs/AGENT_PLAYBOOK.md` for the
  task-card format.
- **Shared boundary**: `models/schemas.py` (Python) <-> `Client/OperationGraphDto.cs` (C#).
  When either side changes the schema, log it in the Handoff Queue.
- **Communication**: write to Handoff Queue below. Both human-driven
  agents read CLAUDE.md before every session.
- **Git**: single repo at `C:\projects\sw-copilot\`. Commit after every
  meaningful change.

---

## Repository Layout

```
C:\projects\sw-copilot\
├── CLAUDE.md                       <- this file
├── README.md                       <- public-facing
├── docs/
│   ├── CHANGELOG.md                <- settled task history
│   ├── SOLIDWORKS_API_REFERENCE.md <- COM signatures (Codex)
│   └── AGENT_PLAYBOOK.md           <- routing + local-agent contract
├── agent-backend/                  <- Python FastAPI (Claude owns)
│   ├── main.py                     <- /generate /validate /ingest /health /version
│   ├── agents/
│   │   ├── macro_engineer.py       <- LLM planner (build_user_message, build_system_prompt)
│   │   ├── rag_agent.py            <- keyword-gated, capped retrieval
│   │   └── validation_agent.py     <- compares OperationGraph vs PartReport
│   ├── standards/dimension_resolver.py  <- ISO 273/4762/4032/7089 lookup tables
│   ├── rag/                        <- ChromaDB wrapper + ingestion
│   ├── knowledge/                  <- 4 .md files auto-ingested at startup
│   ├── models/schemas.py           <- all Pydantic models
│   └── tests/                      <- ~140 tests
└── sw-addin-client/                <- C# .NET 4.8 add-in (Codex owns)
    ├── AddinCore/                  <- COM entry, GUID, ProgId
    ├── UI/TaskPaneHost.cs          <- chat panel, history cap, validation surface
    ├── Client/                     <- BackendClient, BackendRuntime, DTOs
    └── Execution/OperationExecutor.cs  <- 12 op handlers, ~850 lines
```

---

## Current State (2026-05-04)

**Backend:** `178 passed, 9 skipped`. `OperationGraph.schema_version == "0.2"`.
RAG: 37 chunks in ChromaDB, keyword-gated, capped. Endpoints:
`/generate /validate /ingest /health /version`. All token-gated except `/version`.
Multi-provider LLM: NIM (primary when `LLM_PROVIDER=nim`) / Ollama (local fallback) / Groq (default).
Automatic quota fallback: if primary hits 429, tries next provider in `LLM_FALLBACK_CHAIN`.
Currently `.env` defaults to Groq primary + Ollama fallback.

**C# Add-in:** Latest clean build is `Release-beta6`. Beta package:
`artifacts\sw-copilot-beta6.zip`. 12 op types implemented.
Repair-loop, rollback, validation surfacing all wired.

**Local agent:** `qwen2.5-coder:7b` pulled via Ollama. See playbook for usage.

**v0.2 deterministic slice (Codex, 2026-05-04):**
- Implemented `base_plate_v0` for prompts like
  `make a 120x80x10mm base plate with four 6mm holes 10mm from corners`.
- Path is provider-free: prompt -> `DesignSpec` -> `CoordinatePlan` ->
  `SketchGraph` -> v0.2 `OperationGraph` -> deterministic C# executor ->
  `PartReport` -> `ValidationReport` -> `runs/<trace_id>/` artifacts.
- New operation aliases supported by C# executor:
  `create_part`, `create_sketch`, `add_center_rectangle`, `add_circles`,
  `extrude_boss`, `extrude_cut`, `rebuild`.
- Backend tests: `178 passed, 9 skipped`.
- C# compile check: `dotnet build SwCopilotAddin.csproj -c Release
  -p:Platform=x64 -p:RegisterForComInterop=false
  -p:OutDir=...\CodexVerify\net48\` -> `0 Warning(s), 0 Error(s)`.
  Normal Release output was locked by running SolidWorks PID `59660`.
- First live SolidWorks test showed the deterministic JSON path worked, but
  the initial plane contract was wrong (`Top Plane` made a `120 x 10 x 80`
  standing plate). v0.2 now uses SolidWorks `Front Plane` as the XY sketch
  plane so thickness extrudes along model Z. Retest after rebuild/register.
- Retest passed for the base-plate prompt: executor created
  `BasePlate_Extrude`, `Mounting_Holes_Cut`, bbox `120 x 80 x 10`, and
  validation passed.
- Follow-up `add 2mm fillet to all edges` failed three times. This is a
  separate C# edge-selection/fillet executor bug, not a base-plate intent bug:
  the old fillet path collects feature edges broadly and calls
  `FeatureManager.FeatureFillet`; it needs a deterministic body-edge resolver
  for "all edges" and duplicate/invalid edge filtering.
- Deterministic `base_plate_v0` failures no longer auto-repair by regenerating
  the same JSON graph; the UI validates/records trace artifacts and stops.

**Live testing status (Codex owns):**
- Beta6 live test on 2026-05-03 found release blockers. Evidence is also
  mirrored at `C:\AI-Factory\control\.ai\reports\sw-live-test-2026-05-03.md`.
- `make a circle 30mm extrude it 30mm`: produced a 60mm diameter cylinder.
  The planner interpreted bare `30mm` as radius, but user intent should default
  to diameter unless the prompt says radius.
- Front Plane cylinder validation failed because validator expected
  `x=60,y=30,z=60` while actual was `x=60,y=60,z=30`. This indicates
  validation-agent axis mapping is wrong.
- `add four M6 counterbore holes at the top`: planner regenerated sketch +
  extrude and then failed `face_of='ex1'` selection three times. Auto-repair
  repeated the same failing graph twice.
- `delete everything`: removed solid bodies and passed validation, but left
  generated sketches (`Sketch2`, `Sketch3`, `Sketch4`). Needs cleanup or a
  warning rule.
- `create a 50mm wide 30mm deep 20mm tall box`: geometry was correct
  (`x=50,y=30,z=20`), but validator expected `x=50,y=20,z=30`; validation
  swapped depth/height.
- Groq daily quota exhausted during live test. This blocks further LLM-backed
  testing for roughly 30 minutes and proves common primitive/edit flows need
  deterministic no-LLM fast paths before external beta.
- Fillet, chamfer, circular_pattern, linear_pattern, mirror, revolve: not yet
  live-tested because quota was exhausted.

---

## Build / run commands

**Backend (uvicorn):**
```powershell
cd C:\projects\sw-copilot\agent-backend
$p = Get-NetTCPConnection -LocalPort 8001 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -First 1
if ($p) { Stop-Process -Id $p -Force; Start-Sleep -Seconds 1 }
.venv\Scripts\python -m uvicorn main:app --host 127.0.0.1 --port 8001
```

**Backend tests:**
```powershell
cd C:\projects\sw-copilot\agent-backend
.\.venv\Scripts\python -m pytest -q
```

**C# build (close SW first — it locks the DLL):**
```powershell
cd C:\projects\sw-copilot\sw-addin-client
dotnet build SwCopilotAddin.csproj -c Release -p:Platform=x64 `
  -p:RegisterForComInterop=false `
  -p:OutDir=C:\projects\sw-copilot\sw-addin-client\bin\x64\Release-beta6\net48\
```

**Register add-in (elevated PS in `sw-addin-client\`):**
```powershell
.\Register-DevAddin.ps1
```

**Beta package:**
```powershell
cd C:\projects\sw-copilot
.\scripts\Build-BetaPackage.ps1   # -> artifacts\sw-copilot-beta.zip
```

**Local agent (Aider):**
```powershell
aider --model ollama/qwen2.5-coder:7b --no-auto-commits
```

---

## Routing rule (one-line summary)

Scripts -> local Ollama builders for implementation -> Claude Sonnet only for
planner/review through Claude Code. Paid API models are not part of the default
route. Whoever assigns the task **trims context for the receiver**, especially
Qwen which has only 32K. Full rules in `docs/AGENT_PLAYBOOK.md`.

## Release plan

End-to-end release ownership and milestones live in `docs/RELEASE_PLAN.md`.
Current release architecture is:

`prompt -> intent router -> deterministic pattern library -> OperationGraph -> C# executor -> PartReport -> validation`

Intent-to-JSON strategy lives in `docs/INTENT_TO_JSON_STRATEGY.md`. This is
now the priority before expanding SolidWorks feature coverage.

Routing for the next build wave:
- `sw-builder-a`: local Ollama coding builder for backend fast-path router and primary implementation tasks.
- `sw-builder-b`: local Ollama coding builder for secondary implementation, SWIR, tests, and reviewable patches.
- Builders are auto-launch gated: dispatch the project planner first, then builders.
- `md-maintainer`: release gates, dashboards, task-card hygiene, live-test reports.
- `Claude Sonnet`: planner architecture and reviews through Claude Code only, not provider API.
- Human/Codex review: SolidWorks COM details, installer/package, live add-in testing when local agents need review.

---

## Security Model

- Token: `%LOCALAPPDATA%\SwCopilotAddin\backend.token` — 64-char hex,
  regenerated every uvicorn startup.
- All FastAPI routes protected by `X-Copilot-Token` (`secrets.compare_digest`).
- Context strings sanitised before LLM: newlines, backticks, control
  chars, injection markers -> `[REDACTED]`, truncated to 1024 chars. C#
  sends only the file name, not the full local path.
- Pre-execution rule engine refuses geometric impossibilities before COM.
- MacroExecutor (Roslyn) is legacy only — preview dialog + AST denylist,
  never the primary path.

---

## Handoff Queue
*Both agents check this section at the start of every session. Cross items
off when done. Settled items move to `docs/CHANGELOG.md`.*

- [ ] **[Codex -> Claude]** Live test results (C-3): record pass/fail in
  the live testing section above for each remaining op type. If any
  operation fails with a specific COM error, paste it here and Claude
  will fix the Python planner pattern.

- [x] **[Claude]** Beta6 LLM-side fixes (items 1, 3, 5 of the original
  blocker list):
  - (1) Compact system prompt now contains an explicit CIRCLE SIZE DEFAULT
    rule (`Nmm circle` -> diameter -> radius_mm = N/2).
  - (3) Compact system prompt now contains explicit AXIS MAPPING rules for
    Top Plane and Front Plane requests covering wide/deep/tall/long.
  - (5) Repair loop now detects structurally identical operation graphs
    across two LLM attempts (`_normalize_operations`,
    `_repair_loop_repeated`) and appends `_REPAIR_REPETITION_NOTE` to the
    system prompt, forcing the LLM to either switch to a standard plane or
    output noop. Standard plane names survive normalisation so a real fix
    is not flagged as a loop.
  - Files: `agent-backend/agents/macro_engineer.py`.
  - Tests: `agent-backend/tests/test_macro_engineer_prompt.py` — 21 cases
    pinning prompt contract + repair-loop heuristic. Full backend suite
    `165 passed, 9 skipped`.
  - Items (2) and (3-validator) already shipped by Codex this session.
  - Item (4) `delete_feature` orphan-sketch cleanup is C# territory.
  - Item (6) deterministic fast paths for primitives is broader scope —
    Codex already started with `try_fast_path_clarification`. Not in this
    commit.

- [x] **[Codex -> Codex]** SW-B7-004 C# executor hole face resolver fixed:
  `OperationExecutor` now resolves non-plane `hole_wizard.face_of` targets by
  selecting the highest horizontal planar face from feature/body geometry, with
  fallback from stale or invalid feature references to solid body geometry.
  C# build: `0 Warning(s), 0 Error(s)`.

- [x] **[Codex -> Claude]** SW-B7-001 backend validation mapping fixed:
  `validation_agent.py` now validates Front Plane circle extrudes using observed
  beta6 executor behavior (diameter in X/Y, depth in Z). Regression tests added
  for `circle 30mm extrude 30mm`, `circle radius 30mm extrude 30mm`, and
  `50 wide 30 deep 20 tall` box mapping. Scoped backend validation tests:
  `49 passed`.

- [ ] **[Claude -> all]** Local agent (Qwen2.5-Coder-7B) is online via
  Ollama. Configs at `C:\AI-Factory\control\config\litellm.config.yaml`
  and `opencode.json` updated to point at the right model. Routing
  policy and task-card format documented in `docs/AGENT_PLAYBOOK.md`.
  Next step (whoever picks it up): install Aider, write QWEN-TASK-001
  (a small isolated task to validate end-to-end), and report on output
  quality.

- [ ] **[Planner -> all]** Release ownership plan created in
  `docs/RELEASE_PLAN.md`. Active task cards:
  `SW-R1-PLAN`, `SW-R1-001`, `SW-R1-002`, `SW-R1-003`, `SW-R1-004`,
  and `SW-R1-005`. Agents should take these before inventing new scope.

- [x] **[Codex -> all]** SW Copilot v0.2 base-plate slice implemented:
  deterministic `base_plate_v0` parser/compiler added in
  `agent-backend/agents/base_plate_v0.py`; schemas extended for
  `DesignSpec`, `CoordinatePlan`, `SketchGraph`, structured executor results,
  and run artifacts; C# executor now supports coordinate-first sketch aliases
  and appends `Runtime (executor_result): ...`; `/validate` updates saved run
  artifacts when `trace_id` is present. Live test found a plane-contract bug:
  using SolidWorks `Top Plane` produced `120 x 10 x 80`; v0.2 now uses
  `Front Plane` for XY base-plate sketches. Deterministic failures skip
  auto-repair to avoid repeating identical JSON. Tests: backend
  `178 passed, 9 skipped`; C# compile-check build `0 Warning(s), 0 Error(s)`.

- [x] **[Claude]** Multi-provider LLM (quota fix): `macro_engineer.py` now
  supports NIM / Ollama / Groq with automatic fallback on 429 / connection
  errors. Set `LLM_PROVIDER=nim` + `NIM_API_KEY=nvapi-...` in `.env` to test
  NVIDIA NIM through its OpenAI-compatible API. `LLM_FALLBACK_CHAIN=ollama`
  routes quota/connection failures to local Qwen when configured. Provider
  router tests were added in `test_macro_engineer_prompt.py`; full backend
  suite is `178 passed, 9 skipped`. See `agent-backend/config.py` and
  `agent-backend/.env.example` for all settings.

- [ ] **[Claude -> Codex]** SW-FILLET-001: Fix fillet/chamfer edge selector.
  **Root cause diagnosed:** `SelectEdgesForFillet` iterates faces of user
  features and calls `face.GetEdges()`.  The same edge borders two adjacent
  faces, so it gets added to the selection twice.  SolidWorks rejects a
  duplicate-edge fillet selection.  Also, extrude-cut (hole) interior edges
  are selected alongside boss edges — some of those can't be filleted at the
  same radius and cause the whole operation to fail.
  **Fix:** Replace the face-based edge walk with a body-based edge walk:
  ```csharp
  private bool SelectEdgesForFillet(IModelDoc2 doc, string[] featureIds)
  {
      doc.ClearSelection2(true);
      bool anySelected = false;

      if (featureIds == null || featureIds.Length == 0)
      {
          // "all edges" → walk solid bodies to get unique edge set
          IPartDoc part = doc as IPartDoc;
          object[] bodies = part?.GetBodies2(
              (int)swBodyType_e.swSolidBody, true) as object[];
          if (bodies == null) return false;
          var seen = new HashSet<IntPtr>();
          foreach (object bodyObj in bodies)
          {
              IBody2 body = bodyObj as IBody2;
              if (body == null) continue;
              object[] edges = body.GetEdges() as object[];
              if (edges == null) continue;
              foreach (object edgeObj in edges)
              {
                  // Use COM identity pointer for deduplication
                  IntPtr ptr = System.Runtime.InteropServices.Marshal
                      .GetIUnknownForObject(edgeObj);
                  System.Runtime.InteropServices.Marshal.Release(ptr);
                  if (!seen.Add(ptr)) continue;
                  try {
                      ((IEntity)edgeObj).Select4(anySelected, null);
                      anySelected = true;
                  } catch { }
              }
          }
      }
      else
      {
          // Named features: walk their faces (existing logic)
          foreach (string fid in featureIds)
          {
              if (!_features.TryGetValue(fid, out Feature feat)) continue;
              object[] faceArr = feat.GetFaces() as object[];
              if (faceArr == null) continue;
              foreach (object faceObj in faceArr)
              {
                  Face2 face = faceObj as Face2;
                  if (face == null) continue;
                  object[] edgeArr = face.GetEdges() as object[];
                  if (edgeArr == null) continue;
                  foreach (object edgeObj in edgeArr)
                  {
                      try {
                          ((IEntity)edgeObj).Select4(anySelected, null);
                          anySelected = true;
                      } catch { }
                  }
              }
          }
      }
      return anySelected;
  }
  ```
  File: `sw-addin-client/Execution/OperationExecutor.cs`
  Report pass/fail in Handoff Queue after rebuild.

- [ ] **[Claude -> Codex]** SW-CORPUS-001: SolidWorks feature extractor
  (strategic priority). Extend `OperationExecutor.ExtractPartReport()` into a
  batch corpus builder that walks a folder of `.sldprt` files and for each
  part emits a JSON record: `{file, features:[{name,type,suppressed}],
  sketch_entities:[{plane, segments:[{type,startX,startY,endX,endY,...}]}],
  dimensional_constraints:[{dim_type,value_mm,ref1,ref2}]}`.
  API to use:
  - Feature walk: `doc.FirstFeature()` -> `GetNextFeature()` (already done in ExtractPartReport)
  - Sketch entities: cast feature to `ISketch` via `f.GetSpecificFeature2()`;
    call `sketch.GetSketchSegments()` -> returns `object[]` of `ISketchSegment`;
    each segment: `seg.GetType()` (line/arc/circle), cast to `ISketchLine`,
    `ISketchArc`, `ISketchEllipse` for coords in metres.
  - Dimensional constraints: `sketch.GetSketchEquations()` or walk
    `IDisplayDimension` objects from `ISketch.GetDisplayDimensions2()`.
  Output format: JSONL (one record per file), written to a configurable
  output path. This becomes the CAD training corpus.
  Priority: medium — implement after C-3 live testing completes.

- [ ] **[Codex -> Codex]** SW-FILLET-001: Fix follow-up fillet execution.
  Live test after successful `base_plate_v0` creation showed
  `add 2mm fillet to all edges` repeatedly failed with
  `ERROR: Fillet failed — edges may not support this radius`. Root cause is
  likely executor-side edge selection, not planner intent: `ExecFillet()`
  uses `SelectEdgesForFillet()` over broad feature faces and then
  `FeatureManager.FeatureFillet`; follow-up execution has no reliable
  per-run `_features` refs and may select duplicate/invalid edges from
  sketches/cuts. Required fix: add deterministic body-edge selection for
  `feature_ids=[]` / "all edges", filter duplicate edge entities, preferably
  apply external body edges first, and return selected edge count in runtime.
  Add a live-test gate for 2mm fillet on the v0.2 base plate.

---

## Architecture Constraints (never break)

| Constraint | Why |
|---|---|
| `OperationExecutor.Execute()` runs on STA thread | ISldWorks COM is STA-bound |
| Backend at `http://127.0.0.1:8001` | IPv4 explicit; "localhost" may resolve to ::1 |
| All SW COM dimensions in metres | Internal unit. `Mm()` helper converts |
| `dimension_resolver.py` for all ISO numbers | Vector search cannot be trusted for exact dimensions |
| `EmbedInteropTypes=false` on SW interop refs | SW loads from its own dir; embedding breaks COM identity |
| `response_format={"type":"json_object"}` on provider calls | Enforces JSON; retry loop corrects schema failures |
| ChromaDB holds explanatory text only | Exact numbers -> dict in dimension_resolver |
| `_features` dict is per-Execute-call | Cross-request refs fall back to `SelectTopFaceOfBody()` |
