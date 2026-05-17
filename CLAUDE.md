# SW Copilot — Project State (Single Source of Truth)

**Every agent reads this file before touching any code.** Update the
**Handoff Queue** whenever you complete, break, or discover something new.

For settled task history see `docs/CHANGELOG.md`.
For SW COM signatures see `docs/SOLIDWORKS_API_REFERENCE.md`.
For agent routing and the local-agent task-card contract see `docs/AGENT_PLAYBOOK.md`.
For the full SolidWorks part-feature roadmap see
`docs/SOLID_PART_FEATURE_COVERAGE_PLAN.md`.
For the current Codex/Sonnet live-failure fix plan see
`docs/CODEX_LIVE_FAILURE_FIX_PLAN_2026-05-16.md`.

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
6. `OperationExecutor.Execute()` — deterministic SW COM, 15 op types.
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
    └── Execution/OperationExecutor.cs  <- 15 op handlers, ~1100 lines
```

---

## Current State (2026-05-15)

**Backend:** `232 passed, 9 skipped`. `OperationGraph.schema_version == "0.2"`.
RAG: 37 chunks in ChromaDB, keyword-gated, capped. Endpoints:
`/generate /validate /ingest /health /version`. All token-gated except `/version`.
Multi-provider LLM: NIM / Ollama / Groq with automatic quota fallback.

**15 operation types implemented (C# + Python):**
Geometry: sketch, extrude_boss, extrude_cut, hole_wizard, fillet, chamfer,
circular_pattern, linear_pattern, mirror, revolve, delete_feature, noop.
Workflow: update_title_block, export_file, check_drawing.

**Deterministic fast paths:** box_v0.py + cylinder_v0.py + base_plate_v0 + gear + shaft patterns.
All wired into patterns/router.py before LLM call.

**C# Add-in:** Latest clean build is `Release-beta7`. Beta package:
`artifacts\sw-copilot-beta7.zip` (108 MB, SHA256: 7583C585CEA85485ACDB4F643CA2688A0BF4CE7A6434C011671A47C2F4435F4C).
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
  -p:OutDir=C:\projects\sw-copilot\sw-addin-client\bin\x64\Release-beta7\net48\
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

## Product strategy (updated after market research — May 2026)

Full findings: `docs/MARKET_RESEARCH_FINDINGS.md`.

**Primary wedge (ship this first):** Workflow automation — batch exports, title block
updates, drawing pre-checks, standards lookup with citations, macro generation.
This is where engineer pain is real, MecAgent is strongest, and trust is earnable.

**Secondary wedge (after workflow wedge proven):** Constrained geometry generation
from templates (box, plate, shaft, bracket families). Machine-validated only.

**Do NOT lead with:** Free-form natural language → arbitrary new part.
That is the immature, skepticism-heavy part of the field. Defer to Phase 3.

**Pricing target:** $29–49/mo individual; $149–249/mo team seat; Enterprise custom.

## Release plan

End-to-end release ownership and milestones live in `docs/RELEASE_PLAN.md`.
Current release architecture is:

`prompt -> intent router -> [workflow ops | deterministic templates] -> OperationGraph -> C# executor -> PartReport -> validation`

Market research findings live in `docs/MARKET_RESEARCH_FINDINGS.md`. This is
now the controlling product strategy before expanding geometry generation.

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

- [ ] **[Claude -> Codex]** LIVE-BUGS-2026-05-17: User ran live tests and
  found multiple stupid-error issues. Claude fixed the routing bug (see
  below); remaining items need C# work from Codex.

  **Done by Claude (backend, this session):**
  Removed the `try_compile_base_plate_v0` intercept from `main.py:/generate`.
  The legacy `base_plate_v0` parser was intercepting all "plate" prompts
  before `patterns/plate.py` could run — that's why plates extruded to 20mm
  instead of the requested 5mm, and why "plate ... with 4 M6 holes at corners"
  was rejected with "supports exactly four holes". The new `patterns/plate.py`
  router now wins. Also reordered: deterministic pattern matching now runs
  BEFORE the agent-init check, so plates/boxes/etc. work even if LLM agents
  aren't initialised. Backend tests: 371 passed.

  **For Codex (C# OperationExecutor):**

  1. **`delete_feature` cannot find sketches by name.** Live test:
     ```
     You: delete sketch 3
     Agent: [d1] No deletable features found.
     ```
     But `Sketch3` exists in the feature tree report. The C# `ExecDeleteFeature`
     must walk `IModelDoc2.FirstFeature()` -> `f.GetNextFeature()`, match
     `f.Name` case-insensitively against the requested name (`Sketch3`,
     `sketch 3`, `Sketch_3`), then `SelectByName` + `EditDelete`. Also
     accept "delete all sketches" -> delete every ProfileFeature.

  2. **Hole-cut still failing on corner counterbore.** Live test (after
     plate 100x60x5mm):
     ```
     You: m6 counterbore near corners ... one for each corner
     [h1] ERROR: Hole cut failed
     ```
     C# executor returns null from FeatureCut3. Possible causes:
     - Sketch plane resolution after the new `BasePlate_Extrude` feature
     - Counterbore order (pocket first, then clearance through-hole)
     - Through-all flag on a plate only 5mm thick (try blind 5mm if too thin)

  3. **Cross-turn conversation context lost.** Live test:
     ```
     You: m6 counterbore near corners
     Agent: number of holes; say four/4 for all corners
     You: one for each corner       <- merges with prior turn
     [graph emitted, but executor fails]
     You: place 10mm radial from corners
     Agent: number of holes; ...    <- LOST the M6 + "one per corner" context!
     ```
     Verify `TaskPaneHost._history` is sent on every /generate call and that
     the backend's followup parser reads `req.messages[]` to merge partial
     specs across turns.

  4. **Plate now works on the new router** — Codex should re-test after
     rebuilding:
     - `create a 100x60x5mm plate` -> bbox 100x60x5 (NOT 100x60x20)
     - `plate 100x60x5mm with 4 M6 holes at corners` -> 4 corner holes
     - `plate 100x60x5mm with 4 M6 counterbored holes at corners and 2mm fillet on all edges`
       -> compound graph in a single response


- [ ] **[Claude -> Codex]** DETERMINISTIC-COMPILER-V1 (2026-05-17): Backend
  is now a deterministic NL→OperationGraph compiler that covers most common
  engineering requests with zero LLM calls. New patterns shipped:
  `patterns/plate.py`, `patterns/flange.py`, `patterns/bracket.py`,
  `patterns/bushing.py`, plus `patterns/compound_features.py` which appends
  fillet/chamfer from a single-shot compound prompt. New `LLM_DISABLED=true`
  config flag refuses all LLM calls. Failure memory hardened (atomic writes,
  bounded growth, PII scrubbing, dedup, corruption recovery). Multi-provider
  free LLM chain with always-on Ollama fallback. SW feature catalog at
  `agent-backend/knowledge/solidworks_feature_catalog.md` auto-ingested.
  Tests: backend `335 passed, 9 skipped`. C# build `0 Warning(s), 0 Error(s)`.

  **Codex action items when you return:**
  1. **Live-verify each new shape pattern** in SolidWorks (register from
     `C:\Projects\sw-copilot\sw-addin-client`, NOT `C:\Users\theof`):
     - `create a 100x60x5mm plate` — sketch black/fully-defined?
     - `flange 100mm OD 6mm thick with 6 M8 holes on 80mm PCD` — 6 holes
       on 80mm PCD via circular_pattern?
     - `create an L-bracket 80x60x5mm` — two perpendicular plates render?
     - `create a bushing 30mm OD 15mm ID 40mm long` — outer cylinder with
       concentric through-bore?
     - `create a 100x60x10mm plate with 4 M6 holes at corners and 2mm fillet on all edges`
       — single prompt produces complete part?
  2. **Smart Dim popup verification.** I added
     `_swApp.SetUserPreferenceToggle(swInputDimValOnCreate, false)` at addin
     connect AND defensively per Execute() in `OperationExecutor.Execute()`.
     Confirm SolidWorks no longer pops up the Modify dialog on every
     dimension. If it still does, the toggle name may differ in SW2021 —
     try `swInputDimValOnCreate2`.
  3. **Plan-preview dialog skipped by default.** The MacroPreviewDialog is
     now gated by `SW_COPILOT_REQUIRE_CONFIRM=1`. Verify the user only sees
     their part appear, no confirm modal. Roslyn legacy path is still gated
     by the dialog for safety.
  4. **/feedback endpoint wired into TaskPaneHost.** When `Execute()`
     returns a non-recoverable failure, `BackendClient.ReportFailureAsync`
     fires fire-and-forget so the planner learns from the failure. Verify
     by intentionally creating a failure (e.g., shell a sketch-only part)
     then hitting `GET /learn/stats` to see the record.
  5. **Schema compatibility for `bracket_v0` and `bushing_v0`.** Both use
     only existing op types (create_part, create_sketch, add_center_rectangle,
     add_circles, extrude_boss, extrude_cut, rebuild). No new ops needed in
     OperationExecutor. But verify the C# DTO `OperationDto` deserialises
     `add_circles` with a `circles[]` array correctly — there have been
     drift bugs here before.
  6. **Live-test rib + draft + swept_boss** — these were added in the
     previous session but never verified in live SW. Test prompts:
     - `add a 3mm rib in the middle`
     - `add 5 degrees of draft to the side faces`
     - `swept boss from sketch sk1 along path sk2`
  7. **Document tested combinations** in `docs/LIVE_TEST_LOG.md`
     (create the file). Format: prompt | result | screenshot/notes.

- [x] **[Codex -> all]** SOURCE-ROOT-001: Source of truth corrected to
  `C:\Projects\sw-copilot` only. Ignore the accidental home-folder working
  copy under `C:\Users\theof` for build/register/test instructions. Codex
  ported the required C# fixes into the Projects repo: runtime dependency
  guard in `Register-DevAddin.ps1`, C# DTO support for `thickness_mm` and
  `neutral_plane`, shell/rib/draft executor alignment with backend schema,
  manufacturing intent + shell/draft/rib/sweep preview text, fillet COM
  options fix, and fully-defined sketch fallback constraints. Validation:
  `dotnet build .\SwCopilotAddin.csproj -c Release -p:Platform=x64
  -p:RegisterForComInterop=false
  "-p:OutDir=C:\Projects\sw-copilot\sw-addin-client\bin\x64\Release-beta7\net48\"`
  -> `0 Warning(s), 0 Error(s)`; required runtime DLLs including
  `Newtonsoft.Json.dll` are present in `Release-beta7`; scoped backend
  follow-up tests for corner counterbores and top chamfers passed (`2 passed`).
  Next live test must register from
  `C:\Projects\sw-copilot\sw-addin-client`, not from `C:\Users\theof`.

- [ ] **[Codex -> Claude]** SW-LIVE-BOX-HOLES-CHAMFER-001:
  Codex patched the exact failures from the user's live test. Deterministic
  `box_v0` now handles `50mm x 40mm x 30mm box`; the add-in sends active
  `bounding_box_mm`; backend `followup_feature_v0` handles corner holes,
  top chamfers, and fillets without LLM calls; executor resolves stale
  `f1 top` references via feature-name/body-top fallback; top-edge selection
  uses `__top_edges__`; counterbores are two-stage clearance + pocket cuts.
  Tests: backend `260 passed`; add-in verification
  `dotnet build sw-addin-client\SwCopilotAddin.csproj /p:RegisterForComInterop=false`
  -> `0 Warning(s), 0 Error(s)`. Claude next: rebuild/reinstall, run the
  three live prompts in `docs/CODEX_LIVE_FAILURE_FIX_PLAN_2026-05-16.md`,
  and report whether counterbore blind cuts go into the body.

- [ ] **[Codex -> Claude]** SW-SKETCH-DIMS-001: Smart Dimension foundation
  added for primitive sketches. `add_center_rectangle` now attempts explicit
  horizontal/vertical Smart Dimensions, an origin coincident relation, and a
  `SketchManager.FullyDefineSketch` cleanup pass. `add_circles` now attempts
  diameter Smart Dimensions plus circle-center definition dimensions/relations
  before the same cleanup pass. Generic `sketch` operations now run
  `FullyDefineSketch` before close, and `hole_wizard` fallback sketches now
  dimension hole diameters/centers before cutting. `ExtractPartReport()` reports
  `dimension_count` for each sketch, and backend `PartSketchInfo` accepts it.
  Validation done so far: C# build `0 Warning(s), 0 Error(s)`. Live SolidWorks
  verification still required: create box, cylinder, and base plate with holes;
  open sketches; confirm they are black/fully defined and dimensions are
  editable driving dimensions rather than driven clutter. If hole sketches are
  over-defined, Claude/Codex should tune the auto-define pass for circle arrays.
  Attempted PowerShell COM smoke test on 2026-05-16 failed before execution with
  `TYPE_E_ELEMENTNOTFOUND` on `SldWorks.Application` automation calls; use the
  real add-in UI or a checked-in harness for the next live test.

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
