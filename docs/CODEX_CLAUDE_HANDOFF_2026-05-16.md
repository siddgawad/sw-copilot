# Codex -> Claude Handoff: SW Copilot

Date: 2026-05-16

## Product Intent

SW Copilot should become a safe, free downloadable Windows SolidWorks copilot
that proves serious CAD automation capability. The market entry wedge is not
free-form text-to-CAD. Lead with workflow automation and constrained,
machine-validated geometry.

The user goal is a product that can help mechanical engineers and demonstrate
professional SolidWorks automation skill:

- update drawings and title blocks
- export PDFs/DXFs/STEP files
- check drawings for missing fields and obvious quality issues
- create simple fully defined primitives and template parts
- apply features such as extrude, cut, fillet, chamfer, holes, and patterns
- use deterministic standards knowledge for manufacturable dimensions
- avoid unsafe macro execution and avoid uploading CAD files by default

## Source Of Truth

Use `C:\projects\sw-copilot`.

The older `C:\Users\theof\agent-backend` and `C:\Users\theof\sw-addin-client`
tree appears to be part of a broad home-directory git repo. Do not treat that
copy as canonical unless the human explicitly says to merge something from it.

## Current Relevant State

Existing docs already encode the right direction:

- `CLAUDE.md`
- `CODEX_TASK.md`
- `docs\RELEASE_PLAN.md`
- `docs\MARKET_RESEARCH_FINDINGS.md`
- `docs\AGENT_PLAYBOOK.md`

`CODEX_TASK.md` assigns the workflow automation build wave:

1. `update_title_block`
2. `export_file`
3. `check_drawing`
4. deterministic `box_v0` and `cylinder_v0`

Current working tree already contains uncommitted C# edits in:

- `sw-addin-client/Client/OperationGraphDto.cs`
- `sw-addin-client/Execution/OperationExecutor.cs`
- `sw-addin-client/UI/TaskPaneHost.cs`

Those edits appear to improve document requirement handling, drawing-only
operation routing, title-block `description`, and task-pane previews. Do not
overwrite them.

Verification from this Codex session:

- Backend: `260 passed`.
- C# add-in: `dotnet build sw-addin-client\SwCopilotAddin.csproj /p:RegisterForComInterop=false`
  succeeded with `0 Warning(s), 0 Error(s)`.
- Live SolidWorks behavior was not tested in this session.

## 2026-05-16 Smart Dimension Work

Codex started the fully-defined sketch track:

- `add_center_rectangle` now attempts to add explicit horizontal and vertical
  Smart Dimensions to the rectangle sketch, constrain the rectangle center to
  the origin, and run `SketchManager.FullyDefineSketch` as a cleanup pass.
- `add_circles` now attempts to add diameter Smart Dimensions and center
  definition dimensions/relations for each circle, then runs
  `FullyDefineSketch`.
- generic `sketch` operations now run `FullyDefineSketch` before closing.
- `hole_wizard` fallback sketches now attempt diameter Smart Dimensions and
  center definition dimensions/relations before cutting.
- `ExtractPartReport()` now emits `dimension_count` per reported sketch.
- Python `PartSketchInfo` now accepts `dimension_count`.
- `docs/SOLIDWORKS_API_REFERENCE.md` now records the dimension APIs used.

Important: this has compile/test coverage only so far. It still needs live
SolidWorks verification that sketches turn black/fully defined and that the
auto-added dimensions are not over-defining hole sketches.

Live-test attempt:

- SolidWorks is installed under `C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS`.
- Starting `SldWorks.Application` through PowerShell COM failed with
  `TYPE_E_ELEMENTNOTFOUND` on basic automation calls such as `Visible`,
  `NewPart`, and `ExitApp`.
- Attempting a typed inline C# harness also failed to resolve
  `SolidWorks.Interop.sldworks` in the PowerShell/Add-Type load context.
- Any leftover `SLDWORKS` process from the failed attempt was stopped.
- Next live-test path should use the actual add-in inside the SolidWorks UI or
  a small checked-in test harness project that runs from the add-in output
  directory with explicit interop DLL resolution.

## Agent Ownership

## 2026-05-16 Live Failure Fix

Codex also patched the specific live failures the user reported. Full details
and Claude's next tasks are in
`docs/CODEX_LIVE_FAILURE_FIX_PLAN_2026-05-16.md`.

Summary:

- `box_v0` now matches `50mm x 40mm x 30mm box` and sets
  `part_family="box_v0"`.
- Add-in `DocumentContext` now includes active part `bounding_box_mm`.
- Backend `followup_feature_v0` compiles corner holes, top chamfers, and
  fillets without calling an LLM.
- Deterministic `_v0` graphs no longer trigger Groq/NIM repair loops.
- `f1 top` stale references fall back to feature-name/body-top selection.
- `active_top_face` and `__top_edges__` give stable selectors for follow-up
  feature edits.
- Counterbore execution is now two-stage: clearance through-hole plus blind
  counterbore pocket.

Claude next: rebuild/reinstall the current add-in/backend package and run:

1. `create a 50mm x 40mm x 30mm box`
2. `add four M6 counterbore holes at the corners`
3. `add a 3mm chamfer on the top edges`

Expected: no LLM calls for any of the three, first bbox `50 x 40 x 30`, no
`/validate` 404, and no auto-repair request to Groq.

## Agent Ownership

Claude should own:

- backend planner/schema/tests unless Codex is explicitly assigned a backend task
- intent routing and prompt contract
- release docs and task-card clarity
- security review

Codex should own:

- C# SolidWorks COM executor behavior
- add-in UI execution details
- packaging and installer verification
- live SolidWorks testing when available
- build/test verification across the C# boundary

Shared boundary:

- `agent-backend/models/schemas.py`
- `sw-addin-client/Client/OperationGraphDto.cs`

If either side changes operation schema, update both sides and record it in a
handoff doc or `CLAUDE.md`.

## Next Work Order

1. Verify current SW Copilot backend tests:
   `cd agent-backend && .venv\Scripts\python -m pytest -q`
2. Verify C# build:
   `cd sw-addin-client && dotnet build SwCopilotAddin.csproj -c Release -p:Platform=x64 -p:RegisterForComInterop=false "-p:SolidWorksPath=C:\projects\sw-copilot\sw-addin-client\lib\solidworks" --no-restore`
3. If the C# build fails, Codex fixes the C# compile issue first.
4. If backend schema tests fail, Claude fixes Python schema/router tests first.
5. After both pass, live-test workflow operations in SolidWorks:
   - set revision / drawn by / description
   - export active drawing as PDF
   - check active drawing
   - create box
   - create cylinder
   - add fillet/chamfer to generated part

## Product Bar

Before public download:

- no macro injection path in the default flow
- no CAD upload by default
- backend token auth works
- installer/uninstaller works on a clean Windows machine
- every supported prompt either succeeds, previews a safe operation, or gives a
  clear refusal/clarification
- known limitations are explicit in README and release notes
