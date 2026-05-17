# Codex Live Failure Fix Plan - 2026-05-16

This is the current handoff for Claude/Sonnet and any other agent working on
SW Copilot. Read this before changing planner or executor code.

## User Goal

Make SW Copilot reliable enough that a user can build and edit SolidWorks
parts through normal language without quota failures, regenerated duplicate
parts, under-defined sketches, or brittle face references.

Immediate live test failures to fix:

1. `create a 50mm x 40mm x 30mm box`
   - Wrong route: fell through to LLM instead of deterministic `box_v0`.
   - Wrong geometry: produced bbox `50 x 30 x 40`, not `50 x 40 x 30`.
   - Sketch report did not show `dimension_count`, likely old add-in/backend.
   - Validation returned backend HTTP 404.

2. `add four M6 counterbore holes at the corners`
   - Wrong route: generated a fresh box again instead of editing active part.
   - Execution failed selecting `f1 top`.
   - Repair tried Groq and hit 429.

3. `add a 3mm chamfer on the top edges`
   - Fell through to Groq and hit 429.

## Codex Changes In This Pass

Backend deterministic routing:

- `agent-backend/agents/box_v0.py`
  - `50mm x 40mm x 30mm box`, `50 mm x 40 mm x 30 mm box`, and
    `50mm by 40mm by 30mm box` now match deterministic `box_v0`.
  - `box_v0` graphs now set `part_family="box_v0"`.

- `agent-backend/agents/cylinder_v0.py`
  - Deterministic cylinder graphs now set `part_family="cylinder_v0"`.

- `agent-backend/models/schemas.py`
  - `DocumentContext` now accepts `bounding_box_mm`.

- `agent-backend/patterns/followup_features.py`
  - New deterministic follow-up compiler for:
    - `add four M6 counterbore holes at the corners`
    - `add four M6 holes at the corners`
    - `add a 3mm chamfer on the top edges`
    - `add a 2mm fillet on all edges/top edges`
  - Corner hole coordinates are computed from active `bounding_box_mm`.
  - M6 default corner inset comes from `standards.dimension_resolver`.
  - Missing bbox returns a `noop` + `missing_inputs`, not an LLM call.

- `agent-backend/patterns/router.py` and `agent-backend/main.py`
  - Router now has context-aware deterministic handlers before LLM fallback.

Add-in context and execution:

- `sw-addin-client/Client/DocumentContextBuilder.cs`
  - Sends active part `bounding_box_mm` to backend.

- `sw-addin-client/Client/BackendClient.cs`
  - Includes `bounding_box_mm` in `/generate` payload.
  - Gives a useful message for `/validate` 404: likely old packaged backend.

- `sw-addin-client/UI/TaskPaneHost.cs`
  - Any graph with `part_family` ending `_v0` is treated as deterministic.
  - Deterministic failures stop instead of asking Groq for repair.

- `sw-addin-client/Execution/OperationExecutor.cs`
  - `f1 top` / `feature top` now falls back to feature-name lookup, then to
    highest planar body face.
  - `active_top_face` is accepted as a stable face selector.
  - `__top_edges__` selects the active top face boundary edges for top chamfer
    and top fillet requests.
  - `counterbore` holes now execute as two cuts: clearance through-hole plus
    shallow counterbore pocket.

## Verification Already Run

From `C:\projects\sw-copilot\agent-backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Result: `260 passed`.

From `C:\projects\sw-copilot`:

```powershell
dotnet build sw-addin-client\SwCopilotAddin.csproj /p:RegisterForComInterop=false
```

Result: `0 Warning(s), 0 Error(s)`.

Plain `dotnet build sw-addin-client\SwCopilotAddin.csproj` compiles the DLL
then fails at COM registration with `MSB4803` because .NET Core MSBuild cannot
run the .NET Framework `RegisterAssembly` task. Use the command above for
verification and the repo's registration/package scripts for real add-in use.

## Claude Tasks Next

1. Rebuild/reinstall the add-in and packaged backend from current repo, then
   run the exact live test sequence:
   - `create a 50mm x 40mm x 30mm box`
   - `add four M6 counterbore holes at the corners`
   - `add a 3mm chamfer on the top edges`

2. Confirm expected behavior in the UI:
   - First prompt returns deterministic `box_v0`, not Groq/LLM.
   - First part bbox is `50 x 40 x 30` mm.
   - Sketch report includes nonzero `dimension_count`.
   - Second prompt returns deterministic `followup_feature_v0`, does not
     create another box, and does not call Groq.
   - Counterbore operation creates clearance through-holes plus counterbore
     pockets, not through 11 mm holes.
   - Third prompt returns deterministic `followup_feature_v0`, selects top
     edges only, and does not call Groq.
   - `/validate` does not 404. If it does, the running backend/package is old.

3. If live counterbore blind cuts go outward instead of into the body, fix
   `CreateHoleCut` direction for selected top faces in `OperationExecutor.cs`.
   Do not move this into the LLM planner.

4. Extend validation for follow-up operations:
   - `box_v0`: expected bbox already comes from v0.2 rectangle/extrude ops.
   - `followup_feature_v0` holes: compare executor result plus feature count,
     and warn if no sketch dimensions are reported.
   - chamfer/fillet: validate that the requested feature exists and rebuild
     status is success.

5. Continue the full feature coverage plan from
   `docs/SOLID_PART_FEATURE_COVERAGE_PLAN.md`. The next production slice should
   prioritize deterministic templates and robust executor selectors before
   adding more LLM freedom.

## Architectural Rule

For common primitive creation and follow-up edits, Groq/NIM/Ollama must not be
on the critical path. The architecture is:

`prompt -> deterministic router when possible -> OperationGraph -> C# executor -> PartReport -> validation`

The LLM is allowed only for requests outside deterministic coverage, and even
then the executor and validator remain the source of truth.
