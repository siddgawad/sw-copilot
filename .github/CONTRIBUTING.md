# Multi-Agent Development Workflow

This project is developed by multiple AI agents working together. Here's how to set up and contribute:

## Quick Start for New Agents

1. **Read CLAUDE.md first** - Single source of truth for project state
2. **Check Handoff Queue** in CLAUDE.md for current tasks
3. **Review recent commits** before making changes
4. **Commit after every meaningful change** with descriptive messages

## Agent Roles

| Agent | Responsibility | Files |
|-------|---------------|-------|
| **Claude (Opus)** | Backend, schemas, validation, tests | `agent-backend/` |
| **Codex (GPT-5)** | C# add-in, COM execution, UI | `sw-addin-client/` |
| **Qwen (local)** | Isolated mechanical tasks | Task cards only |

## Boundaries

- **Backend (Claude)**: Python FastAPI, LLM prompts, validation, schemas
- **C# Add-in (Codex)**: SolidWorks COM, execution, UI, live testing
- **Shared boundary**: `models/schemas.py` ↔ `Client/OperationGraphDto.cs`

## Git Workflow

```bash
# Before starting work
git pull origin main

# After completing a task
git add <files>
git commit -m "<type>: <what> - <why>"
git push origin main
```

### Commit Message Format

```
fix(fillet): deduplicate edges using COM identity pointers
feat(base-plate): add deterministic parser for v0.2 slice
docs: update RELEASE_PLAN with beta6 status
```

## Testing Checklist

Before pushing:

- [ ] Backend tests pass: `pytest -q`
- [ ] C# build compiles: `dotnet build -c Release`
- [ ] No secrets committed (API keys, tokens)
- [ ] CLAUDE.md Handoff Queue updated

## Live Testing (Codex only)

For SolidWorks testing:

1. Close SolidWorks (locks DLL)
2. Build: `dotnet build -c Release -p:OutDir=...`
3. Register: `.\Register-DevAddin.ps1 -BuildConfig Release`
4. Restart SolidWorks
5. Test in chat, report results in Handoff Queue

## When Things Break

1. **Backend error**: Check `agent-backend/tests/`, add regression test
2. **C# error**: Check SolidWorks COM signatures, rebuild add-in
3. **Validation mismatch**: Compare OperationGraph → PartReport mapping
4. **LLM loop**: Check repair_loop detection in validation_agent.py

## Communication

- Write decisions to **CLAUDE.md Handoff Queue**
- Move settled items to `docs/CHANGELOG.md`
- Major architecture changes → update `CLAUDE.md` constraints section

## Files That Matter

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Project state, handoff queue |
| `agent-backend/agents/macro_engineer.py` | LLM prompt |
| `agent-backend/agents/base_plate_v0.py` | Deterministic parser |
| `sw-addin-client/Execution/OperationExecutor.cs` | COM execution |
| `docs/AGENT_PLAYBOOK.md` | Agent routing rules |
| `docs/RELEASE_PLAN.md` | Release milestones |
