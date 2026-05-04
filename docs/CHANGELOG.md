# SW Copilot — Task Changelog

Settled work, archived from `CLAUDE.md` to keep the always-loaded surface
small. Agents only need this on demand (e.g. "why was X done that way?").

Date format: YYYY-MM-DD. Tasks prefixed `C-` were Codex's, `L-` were Claude's.

---

## 2026-05-03 — Foundation week

### C-1 — Post-execution part report
`OperationExecutor.ExtractPartReport(IModelDoc2 doc)` returns body count,
bounding box (mm), estimated steel mass, feature count, and per-feature
{name, type, suppressed}. Successful `Execute()` calls append
`Runtime (report): {...}` after the final rebuild. Enables the validation loop.

### C-2 — Schema version guard
`OperationGraphDto.SchemaVersion` (mapped from JSON `schema_version`).
`OperationExecutor.Execute()` rejects non-null versions other than `"0.2"`.
Python side: `OperationGraph.schema_version: str = "0.2"` in `models/schemas.py`.

### C-4 — Rollback button
`OperationExecutor._lastCreatedFeatures` tracks features made during the most
recent `Execute()`. `RollbackLastExecute(IModelDoc2?)` selects and deletes
them. `TaskPaneHost` exposes "Undo Last" beside Send. Build: `Release-beta3`.

### L-1 — `schema_version` on Python `OperationGraph`
Added `schema_version: str = "0.2"` to `OperationGraph` in
`agent-backend/models/schemas.py`. Mirrors C-2.

### L-2 — ISO 4032 nuts + ISO 7089 washers
Added `HexNut` and `Washer` dataclasses, `_HEX_NUT` (M3–M30) and `_WASHER`
(M3–M30) tables, and `resolve_hex_nut()` / `resolve_washer()` to
`agent-backend/standards/dimension_resolver.py`. `resolve_all()` and
`build_standards_context()` surface nut WAF/height and washer OD/thickness so
the LLM can reason about stack-up height.

### L-3 — Open-source README
`README.md` at repo root: problem statement, ASCII architecture diagram,
supported ops table, demo prompts, ISO standards table, setup, security,
limitations.

### L-4 — Backend repair loop
`_has_execution_error()` scans the most recent assistant turn for `ERROR:` or
`RULE VIOLATION`. When triggered, `_REPAIR_ADDENDUM` is appended to the system
prompt, instructing the LLM to inspect the prior error and emit a corrected
graph. File: `agent-backend/agents/macro_engineer.py`.

C# auto-resend wired by Codex in `TaskPaneHost.SubmitAsync` via
`ExecuteOperationGraphWithRepairAsync` — detects markers in the executor
result, appends to temporary assistant history, calls `/generate` again for up
to 2 automatic repair attempts. Every repaired graph still requires preview
confirmation. Build: `Release-beta4`.

### L-5 — Resolver + repair-loop regression tests
`agent-backend/tests/test_dimension_resolver.py`: 60 spot checks against ISO
273, 4762, 4032, 7089, 724/965 plus the repair-mode detector.

### L-6 — Post-execution validation agent (pipeline step 7)
`agent-backend/agents/validation_agent.py`: `validate(graph, report,
tolerance_mm)` compares the requested `OperationGraph` against the C#
`PartReport` and emits a `ValidationReport` with categorised discrepancies
(`bounding_box`, `body_count`, `feature_count`, `suppressed_feature`).

Models added to `models/schemas.py`: `BoundingBox`, `PartFeatureInfo`,
`PartReport`, `Discrepancy`, `ValidationReport`, `ValidateRequest`.

Endpoint: `POST /validate` (token-gated). Body
`{operation_graph, part_report, tolerance_mm}` returns `ValidationReport`.

Coverage: bbox derivation for single-extrude graphs (Top/Front/Right Plane),
body-count sanity, feature-count lower bound, suppressed-feature detection.
Multi-extrude graphs safely skip the bbox check.

C# integration in `BackendClient.ValidateOperationAsync()` and
`TaskPaneHost.ValidateExecutionResultAsync()`.

Tests: `agent-backend/tests/test_validation_agent.py` — 17 cases including
tolerance sweep.

### L-7 — Prompt/token-budget hardening
`agent-backend/agents/macro_engineer.py`: extracted `build_user_message()` and
`build_system_prompt()` as pure functions for testing without Groq.

`agent-backend/agents/rag_agent.py`: skips RAG for simple primitive prompts
(keyword-gated), caps retrieval to 4 chunks, caps RAG text to 6000 chars.

`agent-backend/standards/dimension_resolver.py`: caps standards context to
the first 3 fastener sizes in long prompts.

Tests: `tests/test_prompt_budget.py` covers budget, fastener injection,
repair triggering, stale-error handling, RAG gating, RAG caps.

### Sanitiser hardening (cross-cutting)
C# strips full paths to filenames before context upload. C# and Python both
remove newlines/backticks/control chars and redact injection markers.

### Validation/context-budget hotfix
Sketch-only/noop/delete-only graphs no longer fail validation for
`body_count=0`. `TaskPaneHost` and `BackendClient` cap history to
8 messages / 3000 chars and store compact runtime summaries instead of full
PartReport feature trees. Backend trims history defensively, caps RAG to
2 chunks / 2500 chars, lowers Groq max output tokens to 1536, retries short
429 responses twice. Build: `Release-beta5`.

### Red-team architecture hotfix
Multiple holes on a cylinder/round top without PCD or explicit positions now
fast-paths to clarification before Groq. Compact production system prompt
replaces the verbose dev prompt. `OperationExecutor.ValidateGraph()` rejects
overlapping hole positions before COM. `TaskPaneHost` no longer auto-repairs
deterministic `RULE VIOLATION` or `ERROR: Hole cut failed` responses.
Build: `Release-beta6`.

### AI Factory baseline
External command-center created at `C:\AI-Factory`. SW Copilot remains at
`C:\projects\sw-copilot` and is registered in
`C:\AI-Factory\control\.ai\state\projects.json`; no repo move performed.
Project-level Claude agents added under `.claude/agents/`. Project-level
Codex default added under `.codex/config.toml`.
