# SW Copilot â€” Multi-Agent Playbook

How Claude Code planners and local Ollama builders split work without stepping on
each other or burning context. **Read once, then refer back when routing or
preparing a task card for the local agent.**

---

## The four agents

| Agent | Where it runs | Context | Best at | Cost |
|---|---|---|---|---|
| **Claude Sonnet** | Claude Code, human-launched | large | Planning, architecture review, task breakdown | subscription/no project API |
| **Qwen2.5-Coder-7B** | local Ollama | 32K | Coding builders, tests, docs, focused implementation | free/local |
| **Llama 3.2 (small)** | local Ollama | 128K | Log compression, classification, "is this risky?" pre-checks | free |

The rule: **build agents are local/free by default.** Claude Sonnet may plan
through Claude Code, but project build work should not use paid provider APIs
unless the human explicitly approves a single task.

---

## Routing decision flow

1. **Can a script do it?** (`pytest`, `dotnet build`, `git status`,
   `ollama list`) -> no LLM at all.
2. **Is it isolated, single-file, mechanical?** -> Qwen/Ollama. Examples:
   write a regression test, update docs, summarize logs, or make a small parser.
3. **Is it multi-file but routine?** -> local Ollama builder with a tight
   task card and mandatory human review.
4. **Is it cross-cutting, schema-changing, or new abstraction?** -> Claude
   Sonnet planner/reviewer through Claude Code, not provider API.
5. **Did local builders fail twice?** -> human decides whether to rewrite the
   task card, split the task, or manually approve a paid model.

**Never** use paid API models by default. They require explicit human approval.

---
## Local-agent task card contract

Qwen has 32K context. It cannot read CLAUDE.md, the whole repo, and
conversation history all at once. Whoever assigns the task **trims the
context**. Use this format:

```markdown
# QWEN-TASK-NNN: <short title>

## Goal
<one sentence>

## Files to read (paths only â€” Qwen will read them)
- agent-backend/standards/dimension_resolver.py

## Files to modify
- agent-backend/standards/dimension_resolver.py

## Relevant excerpt (if a target file is >500 lines)
<paste the specific function or block â€” saves Qwen from reading 850-line files>

## Acceptance test (must be runnable)
```powershell
cd C:\projects\sw-copilot\agent-backend
.\.venv\Scripts\python -m pytest tests/test_dimension_resolver.py -q
```

## Success criteria
- New tests pass
- No existing test regresses
- No file outside "Files to modify" is touched

## Forbidden
- Do not touch sw-addin-client/
- Do not modify schemas.py
- Do not install dependencies
```

**One-shot, not multi-turn.** Qwen returns a diff and a test result. If it
fails, the assigning agent trims further or escalates â€” don't try to fix
Qwen by chatting.

---

## Running the local agent

Ollama is installed at
`C:\Users\theof\AppData\Local\Programs\Ollama\ollama.exe`.
Coding model: `qwen2.5-coder:7b` (~4.4GB, fits 8GB VRAM).
Small model: `llama3.2:latest` (logs/classification only).

Quick check:
```powershell
ollama run qwen2.5-coder:7b "write a python function that returns the largest of three numbers"
```

For real work, use **Aider** (terminal coding agent, makes git-aware edits):
```powershell
pip install aider-install
aider-install
aider --model ollama/qwen2.5-coder:7b --no-auto-commits
```
Then in the Aider REPL:
```
/add agent-backend/standards/dimension_resolver.py
> add ISO 4014 hex bolt data following the same pattern as the nuts table
```

Aider shows the diff. You review, run tests, commit if good.

---

## Context-management rules (load-bearing)

These rules keep the always-loaded surface small as the project grows.

1. **`CLAUDE.md` is the volatile surface.** Mission, ownership, build
   commands, **handoff queue**, routing rules. Target: under 250 lines.
2. **`docs/CHANGELOG.md` is the archive.** Settled L/C tasks live here.
   Agents read on demand only. Never reference completed task numbers
   from the live handoff queue.
3. **`docs/SOLIDWORKS_API_REFERENCE.md` is reference data.** Read it only
   when touching the executor or COM-facing code.
4. **`docs/AGENT_PLAYBOOK.md` (this file) is the routing manual.** Read
   once at session start; don't keep it in context.
5. **Don't paste full diffs in CLAUDE.md.** Reference commit hashes; the
   next agent runs `git show <hash>`.
6. **Live SolidWorks work evicts the local model from VRAM.** Don't
   invoke Qwen during live add-in testing â€” only between iterations.

---

## Hardware notes (this machine)

- RTX 4060 (8GB VRAM) â†’ 7B Q4 ceiling
- 32GB system RAM â†’ plenty for Ollama + Python venv + dotnet builds
- i9 13th gen â†’ CPU not a bottleneck for any local agent task

If/when you upgrade GPU: `qwen2.5-coder:14b` Q4 (~8.5GB) becomes viable on
12GB+ VRAM. Above 24GB, `deepseek-coder-v2-lite` (16B MoE) becomes viable
and is genuinely competitive with Codex Mini for code work.

