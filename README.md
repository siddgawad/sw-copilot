# SW Copilot

> Natural language → validated operation graph → deterministic SolidWorks execution.
> No macro injection. No hallucinated dimensions. No guessing.

---

## The Problem

Every CAD AI today does one of two things:

1. **Generates a macro script** — and hopes the LLM didn't hallucinate a method name or an M8 hole diameter.
2. **Wraps a chatbot around SolidWorks** — which means the LLM is load-bearing for geometry decisions.

Both approaches fail in production. LLMs confidently produce wrong dimensions, call non-existent API methods, and have no concept of geometric validity.

**SW Copilot is built differently.** The LLM is a compiler frontend. It emits structured intent. Everything after that is deterministic.

---

## Architecture

```
User prompt
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  Python Backend  (agent-backend/)                   │
│                                                     │
│  1. dimension_resolver.py                           │
│     └─ Scans prompt for M3–M30 fastener refs        │
│        Injects exact ISO 273 / ISO 4762 numbers     │
│        before LLM ever sees the prompt              │
│                                                     │
│  2. RAG (ChromaDB)                                  │
│     └─ Retrieves engineering text for context       │
│        Explanatory only — never for exact numbers   │
│                                                     │
│  3. macro_engineer.py  (Groq / LLaMA-3)             │
│     └─ Emits OperationGraph JSON with               │
│        reasoning scratchpad                         │
│                                                     │
│  4. Pydantic validation                             │
│     └─ Schema enforced before any execution         │
└─────────────────┬───────────────────────────────────┘
                  │  HTTP + X-Copilot-Token
                  ▼
┌─────────────────────────────────────────────────────┐
│  C# Add-in  (sw-addin-client/)                      │
│                                                     │
│  5. DTO validation                                  │
│     └─ C# mirrors Python schema exactly             │
│                                                     │
│  6. ValidateGraph()  — rule engine                  │
│     └─ Refuses geometric impossibilities            │
│        before any COM call                          │
│                                                     │
│  7. OperationExecutor.Execute()                     │
│     └─ 12 deterministic SolidWorks COM operations   │
│        No scripts. No eval. No string-built code.   │
└─────────────────────────────────────────────────────┘
```

---

## Supported Operations

| Operation | Description |
|---|---|
| `sketch` | Rectangle or circle on any plane or face |
| `extrude_boss` | Solid extrusion from sketch |
| `extrude_cut` | Cut extrusion (pocket) |
| `hole_wizard` | Drilled / counterbore / countersink holes (ISO sizes) |
| `fillet` | Edge fillet with radius |
| `chamfer` | Edge chamfer with distance |
| `circular_pattern` | Circular feature pattern |
| `linear_pattern` | Linear feature pattern (1D or 2D) |
| `mirror` | Mirror features across plane |
| `revolve` | Revolve sketch around axis |
| `delete_feature` | Remove feature from tree |
| `noop` | Acknowledged but skipped (with reason) |

---

## Demo Prompts

```
create a 50mm wide 30mm deep 20mm tall box
add four M6 counterbore holes at the corners
add a 2mm fillet on all edges
create a 40mm diameter shaft 100mm long
add 6 M5 holes on a 60mm bolt circle
```

The system looks up M5 and M6 dimensions from ISO 273/4762 tables — not from LLM memory.

---

## Standards Data (deterministic, not RAG)

All fastener dimensions come from hardcoded lookup tables — **not** from the LLM and **not** from vector search:

| Standard | Data |
|---|---|
| ISO 273:2003 | Clearance holes M1.6–M30 (close / normal / loose) |
| ISO 4762:2004 | Socket head cap screw counterbore dimensions |
| ISO 10642:2004 | Countersink dimensions (90°) |
| ISO 724 / ISO 965 | Tap drill sizes + minimum thread engagement |

---

## Requirements

**Backend**
- Python 3.11+
- Groq API key (free tier works: `groq.com`)

**Add-in**
- SolidWorks 2021 (tested) — other versions untested
- Windows 10/11 x64
- .NET Framework 4.8

---

## Setup

### 1. Backend

```powershell
cd agent-backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# Create .env
echo GROQ_API_KEY=your_key_here > .env

# Start server
.venv\Scripts\python -m uvicorn main:app --host 127.0.0.1 --port 8001
```

### 2. C# Add-in

```powershell
# Close SolidWorks first
cd sw-addin-client
dotnet build SwCopilotAddin.csproj -c Release -p:Platform=x64 `
  -p:RegisterForComInterop=false `
  -p:OutDir=bin\x64\Release-beta3\net48\

# Register (elevated PowerShell)
.\Register-DevAddin.ps1
```

Open SolidWorks — the Copilot task pane appears on the right.

---

## Security

- Backend generates a 64-char hex token at startup
- Token written to `%LOCALAPPDATA%\SwCopilotAddin\backend.token`
- All API routes require `X-Copilot-Token` header (timing-safe comparison)
- Context strings sanitized before LLM: newlines, backticks, control chars, injection markers redacted, truncated to 1024 chars
- Pre-execution rule engine rejects geometric impossibilities before any COM call
- No macro code execution by default — Roslyn path is legacy and always behind a preview dialog

---

## Limitations

- SolidWorks 2021 only (COM signatures differ across versions)
- Part documents only — assemblies and drawings not supported yet
- Multi-body parts: operations target the primary body
- Cross-session feature references fall back to top-face heuristic
- No post-execution validation yet (planned Week 2)
- LLM output is validated but not formally verified

---

## Project Structure

```
sw-copilot/
├── agent-backend/          # Python FastAPI backend
│   ├── agents/             # LLM planner + RAG agent
│   ├── standards/          # Deterministic ISO lookup tables
│   ├── rag/                # ChromaDB vector store
│   ├── knowledge/          # Built-in engineering reference docs
│   ├── models/             # Pydantic schemas
│   └── tests/              # 48 security + schema regression tests
│
└── sw-addin-client/        # C# .NET 4.8 SolidWorks add-in
    ├── AddinCore/           # COM entry point
    ├── UI/                  # WinForms task pane
    ├── Client/              # Backend HTTP client + DTOs
    └── Execution/           # SolidWorks COM executor (12 op types)
```

---

## Contributing

This is an active early-stage project. If you work in mechanical engineering or CAD automation, issues and PRs are welcome.

The clearest contribution path right now: **test it against your own SolidWorks version** and report which COM calls break. Each confirmed API signature makes the executor more robust.

---

## License

MIT
