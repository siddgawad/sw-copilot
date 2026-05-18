# BRIDGE_PLAN.md

End-to-end build roadmap from current state (commit `7a8e0f9`) to a
**free public demo release** the SOLIDWORKS engineering community will
respect. Targets MVP first (single recorded prompt chain), then a 30-day
beta pilot, then public release.

Owners are the four virtual roles the orchestrator already uses:
- **Planner** — `agent-backend/agents/macro_engineer.py` + patterns/
- **Validator** — `agent-backend/validation/` (build123d) + `agents/validation_agent.py`
- **COM Exec** — `sw-addin-client/Execution/OperationExecutor.cs`
- **Front-End** — `sw-addin-client/UI/TaskPaneHost.cs`, installer, demo collateral

Days = human-days for one focused engineer with claude assist; LLM-only
hours subtract about 40%.

---

## Phase 0 — Foundation Lockdown (3 days)

**Goal:** ship the validation harness end-to-end before adding any new
feature surface. Without Phase 0, every new feature is unverifiable.

| Task | Owner | Days |
|---|---|---|
| Finish `hole_wizard` build123d handler + 4 xfail → pass | Validator | 1.0 |
| Finish `fillet` + `chamfer` build123d handlers + 3 xfail → pass | Validator | 0.5 |
| Finish `circular_pattern` build123d handler + flange parity test pass | Validator | 0.5 |
| Pattern-parity coverage extended to flange, bracket, enclosure, shaft | Validator | 0.5 |
| GitHub repo created, `validation.yml` first run green | Front-End | 0.5 |

**KPIs**
- Validation suite: 0 xfailed.
- Parity tests cover ≥6 deterministic patterns at 0.5mm tolerance.
- CI runs on every PR; green = mergeable.

**Exit gate:** every deterministic pattern produces a bounding box within
0.5mm of its declared dimensions in build123d, in CI, on Ubuntu, in <60s.

---

## Phase 1 — Reliability Pass (5 days)

**Goal:** make the existing feature set bulletproof under live SOLIDWORKS
before chasing new capability. Targets the live-test gaps from `CLAUDE.md`.

| Task | Owner | Days |
|---|---|---|
| Live retest matrix after redeploying current DLL (plate, holes, fillet, delete sketch, modify thickness, chamfer visual) | COM Exec | 1.0 |
| `circular_pattern` C# executor live-tested on flange + 6-hole bolt circle | COM Exec | 1.0 |
| `edit_feature` op type added (modify existing extrude depth) — schema, Python rule, C# executor branch | Planner + COM Exec | 1.5 |
| LLM repair loop measured: 50 failure-injection runs, measure recovery rate | Planner | 0.5 |
| `Instructor` library wrap of LLM call (eliminates JSON retry loop) | Planner | 0.5 |
| Failure-memory effectiveness: cohort test 20 prompts before/after seeding | Planner | 0.5 |

**KPIs**
- First-pass success ≥85% on the 12-prompt "golden script" (see Phase 3).
- LLM JSON parse failures = 0 in 100 consecutive calls.
- Repair loop recovers ≥70% of single-op failures within 2 attempts.

**Exit gate:** golden script runs end-to-end on a clean SW 2021 install in
under 4 minutes, hands-off, with green validation on every operation.

---

## Phase 2 — Drawing & Export Surface (4 days)

**Goal:** lift the demo story from "I built a part" to "I built a part,
drawing, BOM, and STEP/PDF in one chain." This is the differentiator
versus Zoo (mesh-only) and Autodesk Assistant (chatbot-only).

| Task | Owner | Days |
|---|---|---|
| `check_drawing` op live-tested on auto-generated drawing | COM Exec | 1.0 |
| `update_title_block` live-tested (drawn by / revision / description) | COM Exec | 0.5 |
| `export_file` STEP + DXF + PDF live-tested | COM Exec | 1.0 |
| Deterministic pattern: "drawing of <part>" — auto creates standard 3-view drawing | Planner | 1.0 |
| Standards-grounded title block defaults (ISO 7200 fields) | Planner | 0.5 |

**KPIs**
- Single prompt chain: NL part request → 3-view drawing → STEP + PDF export, all in <90s.
- Title block fields populated from manufacturing-intent metadata.

**Exit gate:** demo can produce, on screen, a 3-view drawing + exported
STEP file from one chat session.

---

## Phase 3 — Public Demo Package (4 days)

**Goal:** package, polish, and produce the artefacts that turn the working
project into a credible public release.

| Task | Owner | Days |
|---|---|---|
| NSIS installer compiled (`makensis SW-Copilot-Setup.nsi`) → single signed EXE | Front-End | 1.0 |
| Code-sign certificate (~US $200/yr) applied; binary not flagged by SmartScreen | Front-End | 0.5 |
| GitHub Releases page with versioned artefacts; `SW_COPILOT_GITHUB_REPO` env honoured | Front-End | 0.5 |
| Demo video: 90-second screencast of the golden script | Front-End | 0.5 |
| README rewrite: differentiate vs Zoo `[S15][S16][S17]`, Autodesk `[S18][S19]`, Onshape `[S21]` — lead with "deterministic, standards-grounded, free, SW 2021 desktop" | Front-End | 0.5 |
| ONE-PAGE prompt cheat-sheet (plate, flange, bracket, enclosure, drawing+export) | Front-End | 0.5 |
| Submit to GrabCAD forum, r/SolidWorks, DEVELOP3D tips column | Front-End | 0.5 |

**KPIs**
- Installer downloads, runs, registers add-in, opens SW, executes plate prompt — all on a clean Windows VM in <5 minutes.
- Demo video posted; ≥1 forum thread or community post live.

**Exit gate:** see Go/No-Go checklist below.

---

## Total: 16 days

Parallelisable: Phase 0 Validator work can run in parallel with Phase 1
COM Exec live-testing. Realistic wall-clock with two focused workers ≈
**10–12 calendar days**.

---

## Go/No-Go checklist before public demo

**Geometry**
- [ ] Plate, flange, bracket, enclosure golden scripts all pass build123d parity (0 xfailed)
- [ ] Counterbore on adequate-thickness plate: 4-corner pattern drilled cleanly, 3 consecutive live runs
- [ ] Fillet on linear edges + chamfer on edges: 3 consecutive live runs without manual recovery
- [ ] PCD bolt circle on flange: 6 holes drilled in correct positions, 3 consecutive live runs
- [ ] "Modify thickness" prompt: deletes Boss-Extrude1 and recreates correctly, 3 consecutive live runs
- [ ] "Delete sketch N" finds and removes absorbed sketches, 3 consecutive live runs

**Validation**
- [ ] `pytest agent-backend/tests/ -q` green on Windows venv (current: 385 passed)
- [ ] `pytest agent-backend/tests/validation/ -q` green with 0 xfailed
- [ ] CI workflow green on the public GitHub repo's `main` branch

**Build & install**
- [ ] `dotnet build` clean (0 warnings, 0 errors) in Release-beta config
- [ ] NSIS-compiled `SW-Copilot-Setup-<ver>.exe` artefact produced
- [ ] Installer code-signed (or, if not, README clearly explains SmartScreen prompt)
- [ ] Clean Windows VM install: download → install → open SW → run plate prompt → success, in <5 minutes

**Demo collateral**
- [ ] 90-second screencast posted on YouTube
- [ ] README leads with the differentiation claim citing `[S15][S16][S18][S21]` (paid+cloud, archived, chatbot-only)
- [ ] Prompt cheat-sheet markdown in repo root
- [ ] At least one external post (GrabCAD / r/SolidWorks / DEVELOP3D) live

**Risk acceptance**
- [ ] Known limitations documented (no assemblies, no drawings of assemblies, no thread modelling, SW 2021 only)
- [ ] Failure modes documented with one-line user-facing message each
- [ ] Issue template in GitHub for `live_test_failure`, `installer_friction`, `prompt_not_understood`

If every box is ticked, ship. If any box in Geometry or Build & install is
unticked, do not announce — fix and recheck.
