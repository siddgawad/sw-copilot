# SW Copilot

> **Chat with SolidWorks.** Natural language → validated operation graph → deterministic COM execution.
> No macro injection. No hallucinated dimensions. No guessing.

[![Backend CI](https://github.com/siddgawad/sw-copilot/actions/workflows/backend-ci.yml/badge.svg)](https://github.com/siddgawad/sw-copilot/actions/workflows/backend-ci.yml)
[![C# Build](https://github.com/siddgawad/sw-copilot/actions/workflows/csharp-build.yml/badge.svg)](https://github.com/siddgawad/sw-copilot/actions/workflows/csharp-build.yml)

---

## What it does

Type a request in the SolidWorks task pane. SW Copilot creates parts, updates title blocks, exports drawings, and checks for quality issues — all through live COM API calls.

**No scripts are generated. No macro files are written. Everything executes against the live document.**

```
You: "create a 50mm wide 30mm deep 20mm tall box"
SW Copilot: creates sketch + extrude in the active part document

You: "add four M6 counterbore holes at the corners"
SW Copilot: places holes using exact ISO 4762 dimensions (clearance 6.6mm, counterbore ∅11mm)

You: "set revision to C, drawn by Siddhant"
SW Copilot: writes custom properties to the document

You: "export this as PDF"
SW Copilot: saves a PDF to the same folder as the document

You: "check this drawing for problems"
SW Copilot: reports missing title block fields, empty sheets, dangling dimensions
```

---

## Why it works differently

Every CAD AI tool makes the same mistake: it puts the LLM in the execution path.

**LLMs cannot be trusted for exact dimensions.** They hallucinate screw clearances. They call non-existent API methods. They generate valid-looking code that does the wrong thing.

SW Copilot treats the LLM as a compiler frontend, not an executor:

```
User prompt
    │
    ▼
[dimension_resolver.py]  ←── ISO 273/4762 lookup tables (deterministic, exact numbers)
    │
    ▼
[Groq / LLaMA-3]         ←── emits structured OperationGraph JSON only
    │
    ▼
[Pydantic validation]    ←── schema checked before any execution
    │
    ▼  HTTP + token auth
[C# ValidateGraph()]     ←── geometric rule engine (rejects impossibilities before COM)
    │
    ▼
[OperationExecutor]      ←── 15 deterministic SolidWorks COM operations
```

The LLM outputs JSON. The C# executor runs it. Dimensions come from ISO tables, not the model.

---

## Supported Operations

### Geometry

| Operation | Example |
|---|---|
| `sketch` | Rectangle or circle on any plane or feature face |
| `extrude_boss` | "extrude the sketch 20mm" |
| `extrude_cut` | "cut a pocket 5mm deep" |
| `hole_wizard` | "4 M6 counterbore holes at corners" — uses ISO dimensions |
| `fillet` | "2mm fillet on all edges" |
| `chamfer` | "1mm chamfer" |
| `circular_pattern` | "6 holes on 60mm bolt circle" |
| `linear_pattern` | "3×4 array, 20mm spacing" |
| `mirror` | "mirror across right plane" |
| `revolve` | "revolve the profile 360°" |
| `delete_feature` | "delete everything" |

### Workflow Automation (the high-value wedge)

| Operation | Example |
|---|---|
| `update_title_block` | "set revision to C, drawn by John, date today" |
| `export_file` | "export as PDF with revision in the filename" |
| `check_drawing` | "check this drawing for issues" — advisory only, never modifies |

---

## Demo Prompts to Try

```
# Part creation
create a 50mm wide 30mm deep 20mm tall box
add four M6 counterbore holes at the corners
add a 2mm fillet on all edges
create a 40mm diameter shaft 100mm long
add 6 M5 holes on a 60mm bolt circle

# Workflow automation
set revision to B, drawn by Siddhant, date 2026-05-15
export this drawing as DXF
export as PDF with filename {docname}_Rev{revision}_{date}
check this drawing for problems
set the description to "Mounting Plate Assembly"
```

---

## Quick Install (for a friend)

**Prerequisites:** SolidWorks 2021, Windows 10/11 x64, .NET Framework 4.8

### Step 1 — Get a free API key

Go to [console.groq.com/keys](https://console.groq.com/keys), sign in, create a key. It's free.

### Step 2 — Download the release

Download `sw-copilot-beta.zip` from [Releases](https://github.com/siddgawad/sw-copilot/releases).

Extract it somewhere permanent (e.g. `C:\sw-copilot\`). **Do not run from inside the ZIP.**

### Step 3 — Set your API key

Open `addin\backend\SwCopilotBackend\.env.example`, copy it to `.env` in the same folder, and set:

```
GROQ_API_KEY=your_key_here
```

### Step 4 — Install the add-in

Close SolidWorks. Open PowerShell as Administrator:

```powershell
cd C:\sw-copilot
.\Install-SwCopilot.ps1
```

If your SolidWorks is in a different folder:

```powershell
.\Install-SwCopilot.ps1 -SolidWorksPath "C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS 2022"
```

### Step 5 — Enable in SolidWorks

Start SolidWorks → **Tools → Add-Ins** → check **SW Copilot** → click OK.

The chat panel appears on the right side. Open a part or drawing and start typing.

### Uninstall

```powershell
.\Uninstall-SwCopilot.ps1
```

---

## Developer Setup (build from source)

### Backend

```powershell
cd agent-backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# Create config
echo GROQ_API_KEY=your_key_here > .env

# Run tests (232 tests, ~3 seconds)
.venv\Scripts\python -m pytest -q

# Start server
.venv\Scripts\python -m uvicorn main:app --host 127.0.0.1 --port 8001
```

### C# Add-in

```powershell
cd sw-addin-client
dotnet build SwCopilotAddin.csproj -c Release -p:Platform=x64 -p:RegisterForComInterop=false

# Register (elevated PowerShell — close SolidWorks first)
.\Register-DevAddin.ps1
```

### Build installer package

```powershell
.\scripts\Build-BetaPackage.ps1
# Produces: artifacts/sw-copilot-beta.zip
```

---

## Standards Data (deterministic, not AI)

All fastener dimensions come from hardcoded lookup tables — never from the LLM:

| Standard | Data |
|---|---|
| ISO 273:2003 | Clearance holes M1.6–M30 |
| ISO 4762:2004 | Socket head counterbore dimensions |
| ISO 10642:2004 | Countersink dimensions (90°) |
| ISO 724 / ISO 965 | Tap drill sizes |

---

## Security

- Backend generates a 64-char hex token at startup; all API routes require it
- Context strings sanitized before LLM call (newlines, backticks, injection markers redacted)
- Pre-execution rule engine rejects geometric impossibilities before any COM call
- No macro code generation or execution by default

---

## Limitations

- Tested on SolidWorks 2021 — COM signatures differ between versions
- Part documents primary target; drawing operations (`export_file`, `check_drawing`, `update_title_block`) work on drawings too
- Multi-body parts target the primary body
- No undo for multi-operation sequences yet (individual SolidWorks undo works)

---

## Project Structure

```
sw-copilot/
├── agent-backend/          # Python FastAPI backend
│   ├── agents/             # LLM planner + RAG + fast-path parsers
│   ├── standards/          # Deterministic ISO lookup tables
│   ├── rag/                # ChromaDB vector store (explanatory text only)
│   ├── knowledge/          # Built-in engineering reference docs
│   ├── models/             # Pydantic schemas
│   ├── patterns/           # Deterministic pattern library (gear, shaft, box, cylinder)
│   └── tests/              # 232 tests: security, schema, fast-paths
│
├── sw-addin-client/        # C# .NET 4.8 SolidWorks add-in
│   ├── AddinCore/          # COM entry point
│   ├── UI/                 # WinForms task pane (chat UI)
│   ├── Client/             # Backend HTTP client + DTOs
│   └── Execution/          # SolidWorks COM executor (15 operation types)
│
└── scripts/                # Build and packaging scripts
```

---

## Contributing

This is an early-stage project targeting mechanical engineers who spend time on repetitive CAD tasks.

**The most useful contribution:** test it with your SolidWorks version and report which COM calls behave differently. Each confirmed API signature makes the executor more reliable across installations.

---

## License

MIT
