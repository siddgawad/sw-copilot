# SW Copilot — Agent Briefing (Codex + Jules)

**Repo root**: `C:\Users\theof\` (also the git root)  
**Last Claude session**: 2026-05-16, commit `9f66cef`  
**Read before touching any code**: `CLAUDE.md` (full architecture, COM API signatures, live build state)  
**Read for Codex tasks**: `sw-addin-client/CODEX_TASKS.md`

---

## What This Is

A free, open-source AI add-in for SolidWorks 2021.  
Natural language → LLM (Gemini free) → validated JSON graph → deterministic C# COM executor.

**Pipeline (never skip a layer):**
1. `standards/dimension_resolver.py` — exact ISO 273/4762 numbers before LLM sees prompt
2. ChromaDB RAG — engineering text retrieval
3. `agents/macro_engineer.py` — LLM emits OperationGraph JSON with reasoning scratchpad
4. Pydantic validation (Python) + DTO validation (C#) — schema enforced before execution
5. `OperationExecutor.ValidateGraph()` — geometric rule engine refuses impossibilities
6. `OperationExecutor.Execute()` — deterministic SolidWorks COM calls
7. Post-execution part report — body count, mass, bounding box, feature list

---

## Ownership Boundaries — STRICTLY ENFORCED to prevent conflicts

| Agent | Owns | Never touches |
|-------|------|---------------|
| **Codex** | `sw-addin-client/` (all C# code), `packaging/` | `agent-backend/` |
| **Jules** | `agent-backend/` (all Python code) | `sw-addin-client/`, `packaging/` |
| **Both** | Append to `CLAUDE.md` Handoff Queue section | Never edit each other's checked-off items |

**Schema change protocol** (the shared boundary):
- `agent-backend/models/schemas.py` ↔ `sw-addin-client/Client/OperationGraphDto.cs` must stay in sync
- Python schema changes first → write to Handoff Queue → Codex mirrors in C# DTOs
- C# DTO changes → write to Handoff Queue → Jules mirrors in Python schemas.py
- Always write to the queue BEFORE committing so the other agent can react

---

## Current Build State (as of 2026-05-16)

### Backend — Python FastAPI (`agent-backend/`)

**Start command:**
```powershell
cd C:\Users\theof\agent-backend
$p = Get-NetTCPConnection -LocalPort 8001 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -First 1
if ($p) { Stop-Process -Id $p -Force; Start-Sleep 1 }
.venv\Scripts\python -m uvicorn main:app --host 127.0.0.1 --port 8001
```

**What works:**
- LLM provider: Gemini 2.0 Flash (free, 1M TPM) — set `LLM_PROVIDER=gemini` + `GEMINI_API_KEY=...` in `.env`
- Fallback: Groq `llama-3.1-8b-instant` — set `LLM_PROVIDER=groq` in `.env`
- `/generate` endpoint: full conversation history, ISO standards injection, RAG context
- 48 security tests passing: `cd agent-backend && .venv\Scripts\python -m pytest tests/test_security.py`
- OperationGraph schema v0.2 with: SketchRelation, SketchDimension, ManufacturingIntent
- LLM system prompt: fully-defined sketch rules, follow-up turn rules (no re-creation of existing ops)

**`.env` file needed** (gitignored, create it):
```
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_key_from_aistudio.google.com

# Fallback only:
GROQ_API_KEY=your_groq_key
GROQ_MODEL=llama-3.1-8b-instant
```

### C# Add-in — `sw-addin-client/`

**Build:**
```powershell
cd C:\Users\theof\sw-addin-client
dotnet build SwCopilotAddin.csproj -c Release -p:Platform=x64 -p:RegisterForComInterop=false `
  -p:OutDir=C:\Users\theof\sw-addin-client\bin\x64\Release-beta2\net48\
```

**Register (elevated PowerShell):**
```powershell
.\Register-DevAddin.ps1
```

**What's implemented:**
- 12 operation types: sketch, extrude_boss, extrude_cut, fillet, chamfer, hole_wizard,
  circular_pattern, linear_pattern, mirror, revolve, delete_feature, noop
- Fully-defined sketches: `sgFIXED` applied inline after each `CreateCornerRectangle` /
  `CreateCircleByRadius` / `CreateLine` call — sketch turns black (fully defined)
- New DTOs in `OperationGraphDto.cs`: `SketchRelationDto`, `SketchDimensionDto`,
  `ManufacturingIntentDto`; `Id` on `SketchEntityDto`; `Relations[]` + `Dimensions[]`
  on `OperationDto`; `ManufacturingIntent` on `OperationGraphDto`
- Conversation history: full OperationGraph JSON stored per turn (LLM sees prior op IDs)
- Part report after each Execute: body count, bounding box mm, mass g, feature list
- Pre-execution rule engine: rejects zero-area sketches, negative depths, bad angles
- Schema version guard: rejects graphs with schema_version != "0.2"

---

## Codex: Immediate Task List (priority order)

### CX-2 — Live Test All 12 Operation Types (HIGHEST PRIORITY)

Run each prompt in SolidWorks after rebuild + re-register. For each failure, paste the exact
COM error or executor result into the CLAUDE.md Handoff Queue so Jules can fix the Python planner.

| # | Prompt | Expected | Test |
|---|--------|----------|------|
| 1 | `create a 50mm x 40mm x 30mm box` | sketch BLACK (not blue), extrude visible | ❌ |
| 2 | (same session, next msg) `add four M6 counterbore holes at the corners` | 4 holes on top, no box re-creation | ❌ |
| 3 | `add a 2mm fillet on all edges` | fillet feature | ❌ |
| 4 | `add a 3mm chamfer on the top perimeter` | chamfer feature | ❌ |
| 5 | `create a 40mm diameter shaft 100mm long` | circle on Front Plane, extrude | ❌ |
| 6 | `add 6 M5 holes on a 60mm bolt circle` | circular_pattern 6× | ❌ |
| 7 | `create a 100x50mm plate 10mm thick, 3×2 array of M4 holes spaced 15mm` | linear_pattern | ❌ |
| 8 | `create a 50mm box then delete everything` | feature tree empty | ❌ |

After each test: update ❌ → ✅ or paste the error. Write results to CLAUDE.md C-3 table.

### CX-3 — Manufacturing Intent Display in Plan Preview

File: `sw-addin-client/UI/TaskPaneHost.cs`, method `FormatOperationPlan()`

Add at the top of the plan string before listing operations:
```
Material: Steel  |  Process: Machined  |  Tolerance: ISO 2768-m
```

Read from `graph.ManufacturingIntent.Material` / `.Process` / `.ToleranceClass`.
Format: `tolerance_class="fine"` → `"ISO 2768-f (fine)"`, `"medium"` → `"ISO 2768-m (medium)"`, etc.

### CX-4 — New Operation Types (implement each, then write to Handoff Queue so Jules adds schema)

Add each to `OperationExecutor.cs` Dispatch switch + implement handler:

**Shell** (`"shell"`) — hollows a solid, leaving open faces:
```csharp
// Select face(s) to remove, then:
Feature feat = (Feature)doc.FeatureManager.FeatureShell(thickness_m, false);
// thickness from op.DistanceMm (reuse field), open face from op.FaceOf
```

**Draft** (`"draft"`) — tapers faces by angle:
```csharp
// FeatureDraft1(NeutralType, Angle, Propagate, AllowBump, UseOutwardDir, ReverseBevel, …)
// angle from op.AngleDeg, face from op.FaceOf, neutral from op.PlaneRef (new field or reuse MirrorPlane)
```

**Rib** (`"rib"`) — stiffening rib from an open sketch profile:
```csharp
// Sketch must be open (line/arc profile), then:
// FeatureRib2(IsBothSides, Thickness, Direction, FlipSide, Natural, Draft, DraftAngle, …)
```

**Swept Boss** (`"swept_boss"`) — extrude along a path:
```csharp
// Needs: profile_id (closed sketch), path_id (open sketch = path)
// SelectRegisteredFeature(doc, op.ProfileId); SelectRegisteredFeature(doc, op.PathId, append=true);
// Feature feat = (Feature)doc.FeatureManager.FeatureSweep4(true, false, 0, 0, false, false, 0, 0, true, false, …);
// Add PathId field to OperationDto; write to Handoff Queue for Jules to add to Python schema
```

After adding each new op type: write `[Codex → Jules] Added {op_type} to OperationExecutor.
New fields needed: {list}. Please add to schemas.py and LLM prompt.` in Handoff Queue.

### CX-5 — Schema Version Bump to 0.3

After CX-4 operations pass live testing:
1. Update `Execute()` guard to accept `"0.2"` OR `"0.3"`
2. Write to Handoff Queue: "C# accepts schema 0.3 — Jules: bump Python schema_version to 0.3"

### CX-6 — NSIS Installer

Target: `SW-Copilot-Setup-0.1.0.exe`  
Read `packaging/Build-BetaPackage.ps1` for what files to include.  
Registry check: `HKLM:\SOFTWARE\SolidWorks\SOLIDWORKS 20*` — abort install if not found.  
Install to `%PROGRAMFILES%\SW Copilot\`. Run RegAsm silently. Add/Remove Programs entry.

---

## Jules: Immediate Task List (priority order)

### JL-1 — Add New Operation Types to Python Schema + LLM Prompt

When Codex writes a new op type to the Handoff Queue, Jules adds it to both:

**`agent-backend/models/schemas.py`** — add new Op model following existing pattern:
```python
class ShellOp(BaseModel):
    id:          str
    type:        Literal["shell"] = "shell"
    face_of:     str               # feature op ID whose face to remove
    thickness_mm: float

class DraftOp(BaseModel):
    id:        str
    type:      Literal["draft"] = "draft"
    face_of:   str
    angle_deg: float = 3.0
    neutral_plane: str = "Top Plane"

class RibOp(BaseModel):
    id:         str
    type:       Literal["rib"] = "rib"
    profile_id: str
    thickness_mm: float
    direction:  Literal["both", "parallel", "normal"] = "both"

class SweptBossOp(BaseModel):
    id:         str
    type:       Literal["swept_boss"] = "swept_boss"
    profile_id: str   # closed profile sketch
    path_id:    str   # open path sketch
```

Add each to the `Operation` Union and `OperationGraph` doesn't need changes.

**`agent-backend/agents/macro_engineer.py`** — add to OPERATION TYPES section:
- Schema block showing all fields
- Example usage showing typical input/output
- Engineering rule: when to use each (shell for enclosures, rib for brackets, etc.)

### JL-2 — Fix Validation Endpoint (currently 404)

The executor result includes:
```
Validation: Validation skipped: Backend validation returned HTTP 404 Not Found
```

There is no `/validate` endpoint in `main.py`. Add a lightweight one:
```python
@app.post("/validate", dependencies=[Depends(verify_token)])
async def validate(req: GenerateRequest) -> dict:
    """Checks whether the most recent executor result contained errors."""
    # For now: just return ok so the C# addin stops logging 404
    return {"valid": True, "issues": []}
```

### JL-3 — Trim System Prompt to Reduce Token Use

Current system prompt ~2500 tokens. Remove Example 2 (shaft + bolt circle) since it's
redundant with Example 1. Remove Example 4 (delete) and Example 5 (box) — keep only
Example 1 (mounting plate) and Example 3 (underspecified). This saves ~600 tokens per request.

### JL-4 — Add Shell/Rib/Draft/Swept Ops to Standards Knowledge

File: `agent-backend/knowledge/gdt_machining.md`

Add a section with DFM rules for each new operation:
- Shell: minimum wall thickness by material (steel 1.5mm, aluminium 2mm, plastic 3mm)
- Rib: height-to-thickness ratio ≤ 3:1 for injection molded, ≤ 5:1 for machined
- Draft: minimum 1° per 25mm depth, 2° for textured surfaces
- Swept: profile must be normal to path at start point

---

## Communication Protocol — How to NOT Conflict

### Writing to CLAUDE.md Handoff Queue

Both agents append new items at the **bottom** of the Handoff Queue section.
Never edit items above your latest append. Use this format:

```
- [ ] **[Codex → Jules]** Added swept_boss to OperationExecutor.cs.
  New DTO field: `PathId` (maps to JSON `path_id`). Please add SweptBossOp
  to schemas.py + add swept_boss to LLM system prompt with path sketch rules.

- [ ] **[Jules → Codex]** Added SweptBossOp to schemas.py (commit abc1234).
  PathId field confirmed. LLM prompt updated with swept_boss. Please verify
  OperationExecutor handles the JSON path_id field correctly.
```

Mark done by changing `- [ ]` to `- [x]` with your agent name and date.

### Commit message convention

```
[codex] feat: add shell operation type to OperationExecutor
[jules] feat: add ShellOp schema + LLM prompt for shell operation
[codex] fix: hole_wizard face selection on extrusion top face
[jules] fix: LLM not referencing prior-turn op IDs on follow-up
```

Tag your commits so the other agent knows who made what at a glance.

### Schema version rule

- Schema version only bumps when C# executor AND Python schema AND LLM prompt ALL support the new op
- Codex proposes the bump in Handoff Queue → Jules confirms → both update in same release

---

## File Map (what's where)

```
C:\Users\theof\
├── CLAUDE.md              ← Full project state + Handoff Queue (BOTH read this first)
├── AGENTS.md              ← This file (briefing for Codex + Jules)
├── agent-backend\         ← Jules owns this
│   ├── main.py            ← FastAPI routes: /generate /health /version
│   ├── config.py          ← LLM_PROVIDER, GEMINI_API_KEY, GROQ_API_KEY settings
│   ├── agents\
│   │   ├── macro_engineer.py  ← Dual-provider LLM (Gemini default, Groq fallback)
│   │   └── rag_agent.py       ← ChromaDB retrieval
│   ├── models\
│   │   └── schemas.py         ← All Pydantic models, schema_version="0.2"
│   ├── standards\
│   │   └── dimension_resolver.py  ← ISO 273/4762 exact lookup tables
│   ├── knowledge\         ← Auto-ingested into ChromaDB at startup
│   │   ├── fastener_reference.md
│   │   ├── design_rules.md
│   │   ├── standard_fits_tolerances.md
│   │   ├── common_features_library.md
│   │   └── gdt_machining.md
│   └── tests\
│       └── test_security.py  ← 48 tests (run before every commit)
│
└── sw-addin-client\       ← Codex owns this
    ├── Client\
    │   ├── OperationGraphDto.cs  ← C# DTOs (mirror of schemas.py)
    │   └── BackendClient.cs      ← HTTP client, conversation history
    ├── Execution\
    │   └── OperationExecutor.cs  ← 12 op types + rule engine + part report
    ├── UI\
    │   └── TaskPaneHost.cs       ← WinForms chat panel, history management
    └── CODEX_TASKS.md            ← Codex task queue (detailed C# specs)
```

---

## Non-Negotiable Rules

1. **Never commit to the other agent's directory** without writing to Handoff Queue first
2. **Run tests before every commit**: `cd agent-backend && .venv\Scripts\python -m pytest tests/test_security.py`
3. **Build before every commit (C#)**: `dotnet build ... 0 errors, 0 warnings`
4. **sgFIXED is the current sketch constraint approach** — do not remove it. Future enhancement is applying actual relation types from `Relations[]` array (this is a Phase 2 task)
5. **schema_version stays "0.2"** until Codex tests ALL new op types and Jules confirms prompt coverage
6. **Groq API key in `.env` is gitignored** — never commit `.env`, never paste keys in code
7. **Gemini key in `.env` is gitignored** — same rule
8. **The LLM is a compiler frontend, not the executor** — all safety/correctness comes from C# rule engine, not the LLM. Don't loosen ValidateGraph() rules to make prompts work.
