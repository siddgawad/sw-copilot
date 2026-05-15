# SW Copilot Release Plan

This is the working plan for turning SW Copilot from beta code into a
deployable SolidWorks add-in. The guiding architecture is:

`prompt -> intent router -> deterministic pattern library -> OperationGraph -> C# executor -> PartReport -> validation`

The LLM interprets user language. Deterministic code owns standards, geometry,
schema safety, face selection, feature references, validation, and packaging.

The intent-to-JSON plan is now the controlling technical strategy:
`docs/INTENT_TO_JSON_STRATEGY.md`.

---

## Release Tracks

| Track | Owner | Responsibility | Release Gate |
|---|---|---|---|
| Backend planner | Planner + SW Local Builder A | Intent router, deterministic OperationGraph templates, repair rules, evals | No Groq call for top primitive/edit prompts |
| C# add-in | SW Local Builder B + human review | COM executor, face resolution, rollback, PartReport, install/package | `dotnet build` has 0 warnings and 0 errors |
| CAD intelligence | Codex + Claude | SWIR extractor, feature/body/assembly mining, geometry classification | Current part/assembly can be summarized into stable JSON |
| Validation | Claude / Qwen | Prompt corpus, graph evals, PartReport comparison, regression tests | CI-style eval report passes beta gate |
| Release ops | md-maintainer / human | task cards, beta package, installer docs, live-test matrix | beta zip, install docs, live-test report exist |
| Product/security | Claude + human | privacy policy, telemetry opt-in, API keys, signing, marketplace route | no CAD upload by default; installer is signed before public release |

---

## Milestones

### R0 - Repo Hygiene And Beta7 Stabilization

Goal: make the current repo and package state unambiguous.

- Canonical repo is `C:\projects\sw-copilot`.
- Package output lives under `artifacts\`.
- Build output lives under `sw-addin-client\bin\x64\`.
- Existing beta7 blocker cards must be completed or explicitly deferred.
- No generated artifacts are treated as source.

Exit criteria:

- `CLAUDE.md` Handoff Queue reflects only active blockers.
- All beta7 task cards have owner, status, acceptance criteria, and command.
- C# add-in builds cleanly.
- Backend scoped tests pass.

### R1 - Deterministic Core Before More LLM

Goal: common user commands do not hit Groq/OpenAI.

Status update 2026-05-04:

- First narrow v0.2 deterministic slice is implemented for
  `base_plate_v0`: `120x80x10mm base plate with four 6mm holes 10mm from
  corners`.
- This does not complete the full R1 top-20 prompt target. It proves the
  desired architecture on one coordinate-first family and should be live-tested
  before expanding scope.
- Run traces are written under `runs/<trace_id>/` and ignored by git.

Build a backend `fast_path_operation_graph` layer before the LLM call. It
should produce schema-valid `OperationGraph` for:

- box/block/plate with width/depth/height
- cylinder/shaft with diameter/radius and length/depth
- delete everything, delete last, undo last
- top-face holes on rectangular parts
- PCD holes on circular parts
- fillet/chamfer all edges
- simple circular/linear pattern requests
- clarification noops for ambiguous round-top hole patterns

Exit criteria:

- top 20 beta prompts pass with provider disabled.
- no LLM-generated ISO dimensions.
- repeated failed graph repair stops after fingerprint match.
- primitive/edit commands are covered by tests.

### R2 - SolidWorks Intelligence Layer

Goal: convert live SolidWorks documents into a stable internal representation
for context, validation, and future learning.

Define `SWIR` as:

```json
{
  "document": {"type": "part|assembly", "path_name": "..."},
  "bodies": [],
  "faces": [],
  "features": [],
  "sketches": [],
  "dimensions": [],
  "components": [],
  "mates": [],
  "part_report": {}
}
```

Initial scope:

- part feature tree using feature type, not feature name/order
- body bounding boxes and face geometry tags
- planar/cylindrical face classification
- sketch dimensions where available
- assembly component names, transforms, suppression state, and referenced paths

Exit criteria:

- active part and assembly can be summarized as JSON without exceptions.
- extractor output is small enough to send as backend context.
- no dependence on user-facing feature names for core logic.

### R3 - Eval And Fine-Tuning Readiness

Goal: measure intent-to-JSON behavior before trusting or training any model.

Create datasets:

- prompt -> expected OperationGraph
- prompt + context -> expected OperationGraph
- bad graph + executor error -> repaired graph or clarification noop
- OperationGraph + PartReport -> expected ValidationReport

Training rule:

- Fine-tune only after evals exist.
- Fine-tune only intent-to-OperationGraph behavior.
- Do not fine-tune standards data or geometry rules.

Exit criteria:

- 300+ golden prompts.
- provider-disabled deterministic eval suite.
- provider comparison report for NIM vs Groq vs local Ollama on the same corpus.
- base model vs fine-tuned model comparison report.
- fine-tune dataset is JSONL and excludes secrets/CAD files unless explicitly approved.

### R4 - Private Beta Release

Goal: deploy to trusted testers with controlled telemetry and support loop.

Required:

- signed or clearly marked private-beta installer
- install/uninstall scripts
- version check
- opt-in telemetry
- "Report bad result" button
- provider quota and offline-mode UX
- live-test matrix for SolidWorks 2021-2026 where available

Exit criteria:

- beta package built from clean source tree.
- install and uninstall verified on a non-dev machine.
- at least 10 tester sessions captured with opt-in logs.
- known limitations published.

### R5 - Public Release / Marketplace Path

Goal: prepare for commercial distribution.

Required:

- code-signing certificate
- terms, privacy policy, support channel
- update channel
- billing or license key flow
- SolidWorks partner/add-in review path
- public docs and demo videos

Exit criteria:

- installer signed.
- release notes generated.
- paid/free tier behavior defined.
- support and rollback process documented.

---

## Agent Routing Rules

- Planners must be dispatched before builders. The dashboard launch endpoint
  enforces this gate.
- Each project has two builders. Both builders are local Ollama coding agents
  by default so build work does not depend on paid API calls.
- Planners may use Claude Sonnet through Claude Code / interactive subscription
  only. Do not wire planners to provider API keys.
- Qwen/Ollama gets isolated tests, docs, small parsers, and mechanical
  refactors unless the human explicitly assigns a larger task.
- `sw-builder-a` is SW Local Builder A using `qwen2.5-coder:7b`.
- `sw-builder-b` is SW Local Builder B using `qwen2.5-coder:7b`.
- `ironlog-builder-a` is IronLog Local Builder A using `qwen2.5-coder:7b`.
- `ironlog-builder-b` is IronLog Local Builder B using `qwen2.5-coder:7b`.
- md-maintainer gets release gates, dashboards, task-card hygiene, and live-test reports.
- Claude owns schema, architecture review, privacy/security, and final planner design.
- Codex owns SolidWorks COM details, installer/package work, and live add-in validation.

Every task card must name:

- files to read
- files to modify
- forbidden files
- acceptance criteria
- runnable validation command
- whether live SolidWorks is required
