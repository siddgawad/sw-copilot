# SW Copilot — Multi-Agent Playbook

How Claude, Codex, and the local Qwen agent split work without stepping on
each other or burning context. **Read once, then refer back when routing or
preparing a task card for the local agent.**

---

## The four agents

| Agent | Where it runs | Context | Best at | Cost |
|---|---|---|---|---|
| **Claude (Opus 4.7)** | claude.com | 1M tokens | Architecture, schema design, multi-file reasoning, security review | $$$ |
| **Codex (GPT-5-Codex)** | OpenAI | ~200K | Multi-file C# work, COM integration, packaging, debugging | $$ |
| **Qwen2.5-Coder-7B** | local Ollama | 32K | Boilerplate, single-file refactors, tests, doc updates, log summaries | free |
| **Llama 3.2 (small)** | local Ollama | 128K | Log compression, classification, "is this risky?" pre-checks | free |

The rule: **paid intelligence used only when marginal value is high.**
Local agent picks up cheap work so paid tokens last for hard problems.

---

## Routing decision flow

1. **Can a script do it?** (`pytest`, `dotnet build`, `git status`,
   `ollama list`) → no LLM at all.
2. **Is it isolated, single-file, mechanical?** → Qwen. Examples: write a
   regression test against an existing function, update a docstring, rename
   a variable across one file, summarise a log.
3. **Is it multi-file but routine?** → Codex medium. Examples: add a new
   operation type that touches schema + executor + tests.
4. **Is it cross-cutting, schema-changing, or new abstraction?** → Claude
   (Sonnet for review, Opus only for high-stakes final review).
5. **Did Qwen fail twice?** → escalate to Codex.
6. **Did Codex and Claude disagree?** → final-opus-reviewer.

**Never** Claude Opus first. Opus is the judge of last resort, not a worker.

---

## Local-agent task card contract

Qwen has 32K context. It cannot read CLAUDE.md, the whole repo, and
conversation history all at once. Whoever assigns the task **trims the
context**. Use this format:

```markdown
# QWEN-TASK-NNN: <short title>

## Goal
<one sentence>

## Files to read (paths only — Qwen will read them)
- agent-backend/standards/dimension_resolver.py

## Files to modify
- agent-backend/standards/dimension_resolver.py

## Relevant excerpt (if a target file is >500 lines)
<paste the specific function or block — saves Qwen from reading 850-line files>

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
fails, the assigning agent trims further or escalates — don't try to fix
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
3. **`docs/SOLIDWORKS_API_REFERENCE.md` is reference data.** Only Codex,
   only when touching the executor.
4. **`docs/AGENT_PLAYBOOK.md` (this file) is the routing manual.** Read
   once at session start; don't keep it in context.
5. **Don't paste full diffs in CLAUDE.md.** Reference commit hashes; the
   next agent runs `git show <hash>`.
6. **Live SolidWorks work evicts the local model from VRAM.** Don't
   invoke Qwen during live add-in testing — only between iterations.

---

## Hardware notes (this machine)

- RTX 4060 (8GB VRAM) → 7B Q4 ceiling
- 32GB system RAM → plenty for Ollama + Python venv + dotnet builds
- i9 13th gen → CPU not a bottleneck for any local agent task

If/when you upgrade GPU: `qwen2.5-coder:14b` Q4 (~8.5GB) becomes viable on
12GB+ VRAM. Above 24GB, `deepseek-coder-v2-lite` (16B MoE) becomes viable
and is genuinely competitive with Codex Mini for code work.
