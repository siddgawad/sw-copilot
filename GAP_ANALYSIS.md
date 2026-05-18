# GAP_ANALYSIS.md

Required capability for a credible **free public demo** of a deterministic
NL→SolidWorks add-in, vs SW Copilot as of 2026-05-18 (commit `7a8e0f9` —
build123d Phase 1 foundation landed; Phase 2 handlers stubbed).

Risk legend: ✅ low · ⚠️ medium · ❌ high

---

## A. Geometric coverage

| # | Required capability | SW Copilot today | Gap | Risk |
|---|---|---|---|---|
| A1 | Flat plates with corner holes | 11 deterministic patterns (plate, flange, bracket, bushing, spacer, pipe, enclosure, washer, gear, shaft + compound/followup), 385 passing tests | None for plates/holes core path | ✅ |
| A2 | Counterbore / countersink / tapped holes | `hole_wizard` C# executor working (live test 10mm plate ✅); ISO 4762 dim resolver | Smart guard rejects M6 counterbore on 5mm plate with actionable message | ✅ |
| A3 | Fillet (linear edges) | C# executor with auto-retry + reduced-radius fallback; 1mm fillet on plate live-passed | Hole-rim fillet blocked by planner with explanation | ✅ |
| A4 | Chamfer (linear edges) | Chamfer handler in C#, distance-vs-thickness guard | Live verification of correct application still needed | ⚠️ |
| A5 | Mounting holes via PCD / bolt circle | Pattern code exists; flange + circular_pattern path not yet live-tested end-to-end | `circular_pattern` build123d handler still stubbed | ⚠️ |
| A6 | Modify existing extrude (thickness, length) | LLM rule 27 now tells planner to delete + recreate; no live confirmation yet | No `edit_feature` op type; relies on LLM honouring rule 27 | ⚠️ |
| A7 | Delete-by-name (absorbed sketches) | New `SelectByID2("Sketch3","SKETCH")` fallback shipped uncommitted | Live retest of `delete sketch 3` after redeploy still pending | ⚠️ |
| A8 | Drawings (`check_drawing`, `update_title_block`, `export_file`) | Op types exist in schema; behaviour not live-tested | No drawing demo path in `/generate` | ❌ |
| A9 | Shell / draft / rib / swept_boss | Op types implemented in C# executor | Not in any deterministic pattern; LLM-only | ⚠️ |

## B. Reliability and validation

| # | Required capability | SW Copilot today | Gap | Risk |
|---|---|---|---|---|
| B1 | Headless validation (no SW open) | build123d Phase 1 foundation; 5 smoke + 4 parity tests pass; CI workflow committed | hole_wizard, fillet, chamfer, pattern handlers still stubbed (8 xfailed) | ⚠️ |
| B2 | First-pass success rate on plates / brackets / flanges | Plates ✅, simple holes ✅, counterbore on adequate thickness ✅, fillet linear ✅ | No published statistic from a structured demo script | ⚠️ |
| B3 | Repair loop on execution failure | Max-2 retry on graph error; rollback on partial failure | "Same JSON repeats" guard added; still surfaces failures rather than always recovering | ⚠️ |
| B4 | Failure-memory feedback to next prompt | `learn/failure_memory.py` (440 LOC); LLM system prompt receives recent lesson block | Not exercised in CI; effectiveness unmeasured | ⚠️ |
| B5 | Cross-turn conversation context | `RecordConversation` helper logs even failed turns into `_history` | Live-test confirmation after DLL redeploy pending | ⚠️ |
| B6 | Standards-grounded numeric correctness | `dimension_resolver.py` (410 LOC) — ISO 273 clearance, ISO 4762 counterbore, ISO 286 fits | ISO 7089 washer, ISO 2768 GD&T not yet wired to all handlers | ⚠️ |

## C. UX and install

| # | Required capability | SW Copilot today | Gap | Risk |
|---|---|---|---|---|
| C1 | Single-click installer | 10+ beta zip artifacts + PowerShell `Install-SwCopilot.ps1`; NSIS `.nsi` script written but `makensis` not run | No EXE produced; users still run `.\Install-SwCopilot.ps1` from admin PowerShell | ❌ |
| C2 | Admin re-register without manual elevation | `Register-DevAddin.ps1` requires `#Requires -RunAsAdministrator` | No graceful elevation prompt in installer flow | ⚠️ |
| C3 | Backend auto-start | `BackendRuntime.cs` autostarts `SwCopilotBackend.exe` (PyInstaller); token rotation per launch | OK for dev; antivirus flags PyInstaller payloads regularly | ⚠️ |
| C4 | Task pane chat UI | WinForms task pane (`TaskPaneHost.cs` 829 LOC); plan-preview dialog; Undo button | Looks engineering-grade, not consumer-grade; no syntax highlighting or markdown | ⚠️ |
| C5 | Update check | `BackendRuntime.CheckForUpdateAsync` queries `SW_COPILOT_GITHUB_REPO`/`SW_COPILOT_RELEASE_REPO` for `releases/latest` | No GitHub repo yet configured for releases | ⚠️ |
| C6 | Demo-recording-ready feature reel | Live tests prove plate/holes/fillet golden path | No scripted demo, no recorded video, no documented prompt list | ❌ |

## D. Standards compliance and trust

| # | Required capability | SW Copilot today | Gap | Risk |
|---|---|---|---|---|
| D1 | ISO 273 clearance lookups | M3–M30 in `dimension_resolver`; injected before every LLM call | None | ✅ |
| D2 | ISO 4762 counterbore dims | M3–M24 in resolver; counterbore depth-vs-thickness preflight in C# and Python | None for sizes in table | ✅ |
| D3 | ISO 2768 / GD&T | `knowledge/gdt_machining.md` auto-ingested into ChromaDB; LLM system prompt mentions tolerance class | Not enforced on output; LLM may emit GD&T-naïve graphs | ⚠️ |
| D4 | Manufacturing-intent metadata in output | `ManufacturingIntent` model exists (material / process / tolerance_class) | Displayed in plan preview; not validated against producibility rules | ⚠️ |

## E. Security and operations

| # | Required capability | SW Copilot today | Gap | Risk |
|---|---|---|---|---|
| E1 | Token-protected localhost API | `X-Copilot-Token` header (64-char hex, regenerated each launch); 48 security tests | None | ✅ |
| E2 | Context sanitisation against prompt injection | `_sanitize_context_value` strips control chars, newlines, injection keywords; truncated to 1024 | Covered by `test_security.py` | ✅ |
| E3 | MacroExecutor (Roslyn) hardening | Behind preview dialog + AST denylist; legacy fallback only | OK, not on the main demo path | ✅ |
| E4 | No PII / telemetry leak | Failure memory PII-scrubs writes; no outbound network from add-in except local backend | None | ✅ |

---

## Highest-risk gaps blocking a public demo

1. **C1 / C6** — no signed single-EXE installer and no scripted demo reel. The two things a journalist or recruiter actually clicks. **Hard blockers.**
2. **A8** — drawings demo absent. Without it the demo story is "I built a plate"; with it the story is "I built a part, drawing, BOM, and PDF in one prompt chain." **Differentiator.**
3. **B1** — Phase 2 build123d handlers (hole_wizard, fillet, chamfer, pattern) still stubbed. Without them CI can only catch primitive regressions, not the operations the demo will actually show.

## Lower-risk gaps acceptable for first public demo

- A7 (delete-by-name), A6 (modify thickness), A4 (chamfer visual), A5 (PCD pattern) — each has working code; needs live retest after DLL redeploy.
- B3/B4/B5 — repair loop, failure memory, history record — work in design; effectiveness needs structured measurement, not new code.
- D3/D4 — GD&T validation. Power-user feature, not demo-day blocker.
