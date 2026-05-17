# Codex Briefing — Read This Before Any Code Changes (2026-05-17)

You and Claude were working in **two separate repos** without knowing it.
This document is your single source of truth for where things stand,
what changed in your absence, and what's still on your plate.

---

## TL;DR — three things you MUST know

1. **Only repo from now on: `C:\Projects\sw-copilot`.**
   The other location (`C:\Users\theof\sw-addin-client`) is dead. Don't
   commit there, don't pull from there, don't rebuild from there. It will
   be renamed to `.archive` once we confirm the merged DLL works.

2. **Your recent C# work was preserved.** Claude merged your `theof`
   `OperationExecutor.cs` (hole-layout preflight, chamfer enum fix,
   cleanup helpers) and `BackendRuntime.cs` (update check, boot logic)
   into Projects. **Nothing of yours was lost.** Diff in commit `a95f4cb`.

3. **Stop hook is still active:** "build end-to-end app, tested all
   features with various dimensions/planes/combinations, never restricted
   by LLM, NL→SW C# compiler using machined-design + industry knowledge".

---

## How we got here

Two parallel repos diverged because git remotes were never aligned:

| Path | Owner | Git tip | Status |
|---|---|---|---|
| `C:\Users\theof\sw-addin-client` | You (Codex) | `9302b1f` | **Archived.** SW used to load from here. |
| `C:\Projects\sw-copilot` | Claude | `a95f4cb` | **Source of truth.** All future work here. |

The two histories never shared a common ancestor for several months. SW
was registered against the `theof` path (`HKLM\...\CLSID\{90562616-...}\InprocServer32\CodeBase`),
so Claude's recent Projects work never reached SolidWorks. Your work did,
because SW was loading your DLL.

---

## What Claude merged into Projects from your repo

**Files copied wholesale from theof → Projects (your work, preserved):**

```
sw-addin-client/Execution/OperationExecutor.cs   (+298 lines from your hole-preflight, cleanup, chamfer-enum fixes)
sw-addin-client/Client/BackendRuntime.cs         (+89 lines from your update-check + boot logic)
```

**Files where Projects was ahead (Claude kept Projects version):**

| File | What Projects has that theof didn't |
|---|---|
| `AddinCore/SwAddin.cs` | Smart Dim popup suppression (`swInputDimValOnCreate=false` at connect + per-Execute) |
| `Client/BackendClient.cs` | `/feedback` endpoint wiring for failure memory |
| `UI/TaskPaneHost.cs` | Undo button + persistent OperationExecutor + repair loop + history fix |

**Build result after merge: `0 Warning(s), 0 Error(s)`.** Confirmed clean
at `a95f4cb`.

---

## What Claude built on the backend (Python, all in Projects)

Twelve deterministic shape patterns, zero LLM calls:

```
agent-backend/patterns/
├── plate.py        ← flat rectangular plate + corner holes + compound features
├── flange.py       ← disk + bolt circle on PCD
├── bracket.py      ← L/angle bracket (two perpendicular plates)
├── bushing.py      ← cylinder + concentric through-bore
├── spacer.py       ← round OR square spacer with bore
├── pipe.py         ← long hollow cylinder (OD+ID or OD+wall)
├── enclosure.py    ← box → shell → corner mounting holes
├── washer.py       ← ISO 7089 plain washer auto-resolved from M3-M24
├── gear.py         ← existing
├── compound_features.py  ← appends fillet/chamfer from trailing prompt clauses
├── followup_features.py  ← corner holes / fillet / chamfer on active part
└── router.py       ← orchestrator
```

Plus:
- `agent-backend/learn/failure_memory.py` — atomic writes, PII scrub,
  dedup, eviction, schema versioning. 17 tests.
- `agent-backend/knowledge/solidworks_feature_catalog.md` — 60+ features
  documented and auto-ingested into ChromaDB at startup.
- LLM-disabled mode (`LLM_DISABLED=true` in `.env`) refuses every LLM call.
- Free-only LLM chain with always-on Ollama fallback (never quota-blocked).

**Test totals:** 371 passed, 9 skipped (skipped are live-LLM tests).

---

## What Claude removed (and why)

**Killed `try_compile_base_plate_v0` intercept in `main.py:/generate`.**

The legacy `agents/base_plate_v0.py` parser was hardcoded BEFORE the new
pattern router in `/generate`. It:
- Extruded plates to 20mm regardless of requested thickness
- Rejected `4 M6 holes at corners` with "supports exactly four holes"
- Never accepted compound prompts

Removed at `db7ae13`. Also reordered: pattern routing now runs BEFORE the
agent-init check, so deterministic prompts work even when LLM agents
haven't loaded yet.

`agents/base_plate_v0.py` module is still on disk because its
`update_run_artifacts_after_validation` is used by `/validate`. Its unit
tests still pass. **But it's no longer in the request hot path.**

---

## Live test results from the user (2026-05-17, important)

User ran prompts in SolidWorks against the OLD (theof) DLL. Each result
tells us what to fix:

| Prompt | Result | What needs to change |
|---|---|---|
| `create a 50mm wide 30mm deep 20mm tall box` | ✅ Bounding box 50×30×20, fully-defined sketch | none — confirms `box_v0` works |
| `create a 100x60x5mm plate` | ❌ Extruded 20mm instead of 5mm | **FIXED by Claude** (removed base_plate_v0 intercept). After redeploy, retest. |
| `plate 100x60x5mm with 4 M6 holes at corners` | ❌ Rejected: "supports exactly four holes" | **FIXED by Claude** (new `patterns/plate.py` accepts compound). After redeploy, retest. |
| `m6 counterbore near corners` → `one for each corner` | ❌ `[h1] ERROR: Hole cut failed` | **Your job.** Even with valid positions, FeatureCut3 returns null. See item 1 below. |
| `delete sketch 3` | ❌ "No deletable features found" | **Your job.** See item 2 below. |
| Cross-turn context (M6 → "one for each corner" → "10mm radial") | ❌ Lost M6 across turns | **Your job.** See item 3 below. |

---

## Your action items (C# side — Projects only)

### CX-LIVE-1: `delete_feature` can't find sketches by name

In `Execution/OperationExecutor.cs`, the current handler returns
`"No deletable features found"` when asked to delete `Sketch3` even
though the feature tree clearly contains it.

**Fix:** make `ExecDeleteFeature` walk `IModelDoc2.FirstFeature()` →
`f.GetNextFeature()` and match `f.Name` case-insensitively against
common name variants: `Sketch3`, `sketch 3`, `Sketch_3`, `sketch3`.

Also accept `delete all sketches` → iterate features, select every
`ProfileFeature`, delete each. The backend already emits a `delete_feature`
op for these requests; your job is just to find and delete them on the
SW side.

### CX-LIVE-2: Hole cut fails on M6 counterbore corners (thin plate)

After `create a 100x60x5mm plate`, asking for M6 counterbore at corners
emits a valid graph (4 positions, ISO 4762 dimensions) but
`FeatureCut3` returns null in your executor.

Plate is only 5mm thick. Possible causes to check:
- Sketch plane resolution — is the hole sketch landing on the top face
  of `Boss-Extrude1`/`base_profile` correctly?
- Counterbore order — your `ExecHoleWizard` cuts the **pocket first** (larger
  diameter, blind), then the clearance through-hole (smaller, through-all).
  Confirm this order is still in the merged code.
- For 5mm plates, the M6 counterbore depth (6mm per ISO 4762) is DEEPER
  than the plate. The cut requires the counterbore to be at most 5mm, or
  the operation must reject early with a clear error.

Your existing hole-layout preflight (now in Projects) is good — but it
checks position overlap, not depth-vs-thickness. **Add a counterbore
depth-vs-plate-thickness check** in the preflight: if
`requested_cb_depth > active_part_thickness - 1mm`, fail early with a
human-readable error suggesting the user pick a tapped or simple hole
instead.

### CX-LIVE-3: Cross-turn conversation context lost

Live test:
```
You: m6 counterbore near corners
Agent: number of holes; say four/4 for all corners
You: one for each corner
Agent: [emits graph using M6 from prior turn — good]
[graph fails to execute due to CX-LIVE-2]
You: place 10mm radial from corners
Agent: number of holes; say four/4 for all corners   ← LOST M6 + "4 corners" context!
```

Two possibilities, both need verifying in your code:

1. **`TaskPaneHost._history` is not being sent on every call.** Confirm
   that `BackendClient.GenerateAsync` always passes the full
   `_history` list as `messages[]` on every request.

2. **`_history` is being cleared after a failed execution.** Some failure
   paths in `TaskPaneHost.SubmitAsync` may not record the turn into
   `_history`. The failed turn (M6 + corners) needs to stay in history
   so the next turn can merge with it.

Backend side (Claude's followup parser at
`patterns/followup_features.py`) already reads `req.messages[]` and
merges partial specs across turns. The bug is almost certainly that
the C# side isn't sending history when execution failed.

---

## How to deploy your fixes once you're done

The DLL is currently loaded from `C:\Users\theof\sw-addin-client\bin\...`
because that's what's registered. Until we re-register against Projects,
use the deploy script:

```powershell
# 1. Close SolidWorks
# 2. Build Projects
cd C:\Projects\sw-copilot\sw-addin-client
dotnet build SwCopilotAddin.csproj -c Release -p:Platform=x64 `
  -p:RegisterForComInterop=false `
  -p:OutDir="C:\Projects\sw-copilot\sw-addin-client\bin\x64\Release-beta2\net48\"

# 3. Deploy to theof's registered location (no admin needed)
C:\Projects\sw-copilot\Deploy-FromProjects.ps1

# 4. Open SolidWorks. The merged-and-rebuilt DLL is now loaded.
```

**Eventually we should re-register from Projects with admin.** That's
your last step in this work block: run
`C:\Projects\sw-copilot\sw-addin-client\Register-DevAddin.ps1` from an
elevated PowerShell. Then delete `C:\Users\theof\sw-addin-client` entirely.

---

## Tests you should run before claiming done

**Schema layer (Claude's tests, must still pass):**
```powershell
cd C:\Projects\sw-copilot\agent-backend
.\.venv\Scripts\python.exe -m pytest tests/ -q
# Expect: 371 passed, 9 skipped
```

**Build (must be 0/0):**
```powershell
cd C:\Projects\sw-copilot\sw-addin-client
dotnet build SwCopilotAddin.csproj -c Release -p:Platform=x64 `
  -p:RegisterForComInterop=false
# Expect: 0 Warning(s), 0 Error(s)
```

**Live tests (the proof — record results in `docs/LIVE_TEST_CATALOG.md`):**
```
1. create a 100x60x5mm plate
   Expected: bbox 100x60x5 (NOT 100x60x20)

2. plate 100x60x5mm with 4 M6 holes at corners
   Expected: 4 corner holes drilled cleanly

3. plate 100x60x5mm with 4 M6 counterbored holes at corners and 2mm fillet on all edges
   Expected: compound graph executes in ONE prompt — holes + fillet

4. delete sketch 3
   Expected: Sketch3 actually deleted from the feature tree

5. create a 100x100x40mm enclosure with 2mm walls and 4 M3 holes at corners
   Expected: box + shell + 4 mounting holes
```

---

## Why this matters (industry context the user gave Claude)

The user is using this project for **job applications**. The story is
*"deterministic NL→CAD compiler with optional LLM"* — a strong portfolio
piece if (and only if) the demo is bulletproof. Currently the demo flow
fails on prompts 2 and 4 above.

Goal for the next user session: clean run of prompts 1-5 above, end to
end, on the merged DLL deployed from Projects. That's the
demo-recording-ready milestone.

---

## Where to write your handoff messages back

Append to `CLAUDE.md` → "Handoff Queue" section. Claude reads it at the
start of every session. **CLAUDE.md is at `C:\Projects\sw-copilot\CLAUDE.md`**
— make sure you're editing the right one.
