# Research Brief: Make `sw-copilot` Solve a Real Problem

> **How to use this prompt**: paste the entire file into a Deep Research agent
> (Claude, GPT-5, Gemini, Perplexity Pro). Do not summarise — every section is
> load-bearing. The agent must produce the deliverables listed at the end
> and print `RESEARCH_COMPLETE` only after all are written.

---

## 1. Mission

I built an open-source SolidWorks add-in called `sw-copilot` (GitHub:
`siddgawad/sw-copilot`). It compiles English prompts into deterministic
SolidWorks operation graphs, executed via COM API against the desktop
2021–2026 install base, grounded in ISO standards (273 / 4762 / 2768 /
21920-1), validated headlessly in build123d (OCCT). It works today for a
narrow surface (plates, brackets, flanges, holes, fillets, edits) and I
want to know what the **single highest-value problem** is that this
architecture can credibly solve in the next 30–60 days, and exactly how
to ship that solution to maximise reach in the mechanical-engineering
community.

This research must end with concrete, source-backed, actionable
recommendations — not a literature review. Decisions, not surveys.

---

## 2. What already exists (don't research things we have)

### Architecture
- **Python FastAPI backend** (`agent-backend/`):
  - 12+ operation types (`create_part`, `create_sketch`, `extrude_boss`,
    `extrude_cut`, `hole_wizard`, `fillet`, `chamfer`, `circular_pattern`,
    `linear_pattern`, `mirror`, `revolve`, `shell`, `draft`, `rib`,
    `swept_boss`, `delete_feature`, `edit_feature`, `update_title_block`,
    `export_file`, `check_drawing`, `generate_macro`, `noop`, `rebuild`)
  - 11 deterministic patterns (`plate`, `flange`, `bracket`, `bushing`,
    `spacer`, `pipe`, `enclosure`, `washer`, `gear`, `shaft`, compound +
    follow-up features)
  - 7 sketch entity types (line, circle, rectangle, arc, ellipse,
    polygon, spline) — full SolidWorks-grade 2D coverage
  - ISO-grounded `dimension_resolver` (M3–M30 clearance / counterbore)
  - LLM fallback chain (Groq → Gemini → NIM → OpenAI-compat → Ollama),
    always-on local Ollama fallback, JSON repair via `json-repair`
  - Failure memory with PII scrub, repair loop (2 retries), token-protected
    localhost API, context sanitisation against prompt injection
  - `build123d` headless validation backend, 408 tests passing
  - GitHub Actions CI validating every PR on Ubuntu, no SOLIDWORKS needed

- **C# .NET 4.8 SolidWorks add-in** (`sw-addin-client/`):
  - `OperationExecutor.cs` (~3400 lines) — 12 op handlers, pre-execution
    rule engine, body-aware bounds validation, counterbore/fillet
    impossibility guards, sketch fix-up, rollback after partial failure,
    absorbed-sketch deletion via `SelectByID2`
  - WinForms task pane with plan-preview dialog, Undo button, repair loop
  - Backend auto-launch (PyInstaller bundle), token-rotated per session,
    update check against GitHub Releases
  - Installer: PowerShell-based (`Install-SwCopilot.ps1`) + NSIS script
    written, not yet compiled

### Decisions already made
- We target **desktop SOLIDWORKS 2021–2026**. We do **not** target
  3DEXPERIENCE cloud. Dassault's AURA AI lives there; we do not compete
  on cloud.
- We are **free + Apache/MIT** for the parts we control.
- We **prefer determinism over LLM creativity**. Patterns first, LLM
  fallback second, deterministic validation always.
- We accept that we are **not Zoo.dev** (closed model, generic mesh,
  paid). We are **not MecAgent** (paid macro generator). We are
  **not Dassault AURA** (cloud-only). We are the gap they don't fill.

### Live-tested working flows (commit `78b3e5b`)
- `create a 100x60x5mm plate` → bbox X=100, Y=60, Z=5 ✅
- `make 4 M6 holes at corners` → 4 holes drilled ISO-correctly ✅
- `make 4 M6 counterbore holes at corners` on 10mm plate ✅
- `fillet all edges 1mm` ✅
- `make 4 M6 counterbore holes at corners` on 5mm plate → correctly blocked
  with actionable error citing ISO 4762 depth ✅
- `fillet circular edges` → correctly blocked with explanation of why ✅
- `delete sketch 3` → handles absorbed sketches via SelectByID2 ✅

### Known gaps (do not re-discover — design around these)
- No drawings / BOM / DXF / PDF export demo path
- No sheet metal pattern (sheet metal is the #1 manufacturing surface)
- No assembly-level operations (every op targets a single part)
- No saved-automation library (every prompt is one-shot)
- No signed single-EXE installer (PowerShell script only)
- No 60-second recorded demo
- No GitHub Release with versioned download
- LLM path JSON failures still possible (mitigated, not eliminated)

---

## 3. What we already researched (don't repeat these citations)

The repo contains four artefacts you may reference but should not re-derive:

- `VALUE_EVIDENCE.md` — economic value dossier, ~700 words, 28 citations
- `GAP_ANALYSIS.md` — capability × today × gap × risk table
- `BRIDGE_PLAN.md` — Phase 0–3 build plan, 16 days, Go/No-Go checklist
- `RESEARCH_SOURCES.json` — 33 sources S01–S33 (load-bearing baselines below)

### Key numbers already established
- 33% of mechanical engineer time = non-value-added (Tech-Clarity n=228) [S01]
- 2.2% of revenue lost to scrap; 10–30% COPQ (ASQ benchmarks) [S05]
- 8M SOLIDWORKS users, 44% of new MCAD seats in 2024, ~285K commercial
  customers (Dassault 2024 URD) [S10]
- Zoo Text-to-CAD pricing: US$0.50/min, $0.08–$0.25/prompt; only UI is
  open-source (276 stars, archived Jan 2026) [S12][S16]
- AI macros pass ~30% first try; ~80% with type-library signatures [S26]
- AURA / LEO / MARIE launching mid-2026, cloud-only [S27]
- 73% of drawing reviews automatable, 96% plan AI adoption in 1–2 years
  (Capvidia/DEVELOP3D, n=250) [S29]
- SOLIDWORKS 2026 `AutoGenerate Drawing` is **BETA**; not GA

### Competitive landscape locked
- **Zoo.dev** — paid, cloud, single-object mesh focus, archived OSS UI
- **MecAgent** — paid, closed, generates reusable macros + UI dialogs,
  strong batch / shop-floor / export workflows. Demo video shows:
  batch DXF export of sheet-metal parts, drawing-text search/replace,
  bulk hole resize, surface area sum, raw-material total
- **Autodesk Fusion AI / Forma / Project Bernini / Neural CAD** — chatbot
  + research; no commercial NL→parametric CAD product
- **PTC Onshape AI Advisor, Creo 12 AI** — chatbots only, no NL→geometry
- **Dassault AURA / LEO / MARIE** — Mistral-Small-3.1 powered, summary +
  conversational, **3DEXPERIENCE only**, **not desktop SW**
- **Open weights for parametric MCAD** — do not exist (CAD-MLLM released
  eval code + dataset only; BlenderLLM targets Blender Python)
- **Academic**: Seek-CAD, STEP-LLM — research, no tooling

---

## 4. Research questions — answer each one with sources

### Q1 — The single highest-leverage problem
Of the documented mechanical-engineering pain points (drawing creation,
hole call-outs, ECO cycle, sheet-metal flat patterns, drawing review,
GD&T compliance, BOM generation, fastener selection, configuration
management, design-to-manufacturing handoff), which **one** has:
- Highest dollar value lost per occurrence
- Highest frequency in a typical week for a mid-size manufacturer
- Lowest competition from incumbents *for the desktop SW install base*
- Cleanest match to our architecture (NL → deterministic op graph → COM)
- Highest "demo-ability" on a 60-second video

Score each candidate on those five axes 1–5, sum, recommend the winner.
Show your scoring.

### Q2 — The viral wedge demo
What single 30–60-second prompt → result demo, run on stock SOLIDWORKS
2021–2026 desktop, would produce the highest engagement on:
- r/SolidWorks (browse 2025–2026 top posts, identify what consistently
  hits >100 upvotes)
- r/AskEngineers / r/cad / r/manufacturing
- LinkedIn engineering posts (cite recent viral SW posts and what made
  them work)
- Hacker News (cite recent `Show HN` engineering tool launches and their
  hit/miss patterns)
- Engineering YouTube (Joel Telling, GoEngineer, Hawk Ridge demos)

Recommend the exact prompt to use, the exact part to build, and the
exact filming approach. Cite at least three concrete viral posts from
2025–2026 that prove the format works.

### Q3 — Distribution channels for a mechanical-engineering tool
Identify the top **5 channels** where the SOLIDWORKS desktop community
actually congregates and trades tool recommendations in 2025–2026.
For each:
- Channel name + URL
- Monthly active mechanical engineers (estimated, with method)
- Cultural rules (what gets upvoted vs banned)
- Specific contact (moderator handle, editor name, prolific contributor)
- Best post format for the channel
- Sample copy of an inaugural launch post for sw-copilot

Skip generic "post to social media". Be specific.

### Q4 — Real engineer pain interviews
Pull 10–15 specific 2025–2026 posts from r/SolidWorks /
r/AskEngineers / engineering forums / GrabCAD where mechanical
engineers explicitly describe a repetitive CAD pain point. For each:
- Direct quote
- URL
- Could sw-copilot solve it today / with 1 week of work / not at all
- If solvable, what's the exact feature to add

Bias toward posts with **>50 upvotes or >20 comments** — proof of
shared pain.

### Q5 — Monetisation paths that don't kill OSS positioning
We will NOT close-source the core. We may consider:
- GitHub Sponsors
- A paid "Pro" companion (e.g. cloud-stored automation library)
- Consulting hours for paid customisation
- Grants (Mozilla, NLnet, OSS Fund, DSEC, MSR, NSF SBIR)
- Bounties from individual companies for specific patterns

Rank these by realistic 12-month revenue ceiling for a project at our
size (low star count today), with concrete grant URLs, sponsor program
URLs, and at least one example of a similar-sized engineering OSS
project that has succeeded with each path. Skip Patreon, Buy Me a
Coffee, OpenCollective unless you can cite >$5K/yr from a comparable
engineering tool.

### Q6 — Closing the 5 hard gaps
For each of the five known gaps below, find:
- The best published solution / library / tutorial / blog post that
  closes it for our stack
- The estimated dev-time to integrate
- Any non-obvious gotcha

Gaps:
1. NSIS-compiled signed single-EXE installer for a SW add-in
   (specifically: avoiding SmartScreen flag without paying Sectigo $300)
2. Drawings auto-generation from a part (3 standard views + dimensions
   + title block + BOM) via SolidWorks COM
3. Sheet metal flat pattern → DXF export via SolidWorks COM
4. AI hole recognition on an imported STEP file (detecting cylindrical
   features and labelling them with ISO callouts)
5. Multi-part / assembly-level operations from a single prompt

### Q7 — Anti-patterns to avoid
What have similar AI-CAD projects shipped that **failed** publicly in
2024–2026, and why? Look for:
- Hacker News launches that flopped
- Indie tools that got <100 stars
- Trade-press dismissals of generative-CAD attempts
- Engineering-blog "I tried X and it sucks" posts

Synthesise 5–7 anti-patterns. Each = one sentence rule, one citation.

### Q8 — The 30-60-90 day plan
With the answers from Q1–Q7, draft a concrete 30 / 60 / 90 day plan
with weekly deliverables, owner (Planner / Validator / COM Exec /
Front-End / Marketing), and a single quantitative goal per period
(stars, weekly active users, demo views, whatever you justify with
sources).

End with a one-page "If only one thing happens this quarter, it should
be: ___" recommendation.

---

## 5. Constraints — these are non-negotiable

- **Desktop SOLIDWORKS 2021–2026 only**. Do not propose cloud / 3DEXP /
  web-only architectures.
- **Open-source core (Apache or MIT)**. Closed-source forks are off the
  table.
- **No paid LLM API as a hard dependency**. Local Ollama fallback must
  always work. Cloud LLMs (Groq, Gemini) are accelerators, not
  requirements.
- **No 3D printing focus**. The user base is mechanical / sheet-metal /
  fixture / fastener engineering, not maker / consumer 3D printing.
- **No "build a CAD kernel" recommendations**. We use SW + OCCT, not
  our own.
- **No model training**. We don't have the GPU budget. Fine-tuning
  proposals are not allowed.
- **Skeptical of incumbent vapor**. Treat any "coming soon" feature
  from Dassault / Autodesk / PTC as not-shipped until you can cite a
  GA release date.

---

## 6. Deliverables — produce all of these or the research is incomplete

Write these four files into the repo root:

1. **`SOLUTIONS_HIGH_VALUE_PROBLEM.md`** — answer to Q1 + Q4. 700 words
   max. Scoring table. Top 3 problems ranked. Winner explained in one
   paragraph. Each claim source-tagged with S## continuing from S33.

2. **`SOLUTIONS_LAUNCH_PLAYBOOK.md`** — answer to Q2 + Q3. The exact
   demo script (prompt + filming notes), the exact 5 channels with
   moderator/editor names and copy, anti-patterns from Q7 inline as
   "do not do" boxes.

3. **`SOLUTIONS_GAP_CLOSURES.md`** — answer to Q6. One subsection per
   gap. For each: tool/library/tutorial URL, dev-time estimate,
   gotchas.

4. **`SOLUTIONS_30_60_90.md`** — answer to Q8. Calendar-style. Owner
   per row. One-page "if only one thing" recommendation at the bottom.

5. **`SOLUTIONS_SOURCES.json`** — extension of `RESEARCH_SOURCES.json`,
   continuing IDs from S34 onwards. Same schema.

6. Print exactly `RESEARCH_COMPLETE` when all five files exist and pass
   citation-integrity check (every S## referenced in markdown exists in
   the JSON).

---

## 7. Quality bar

- **Citations**: every quantitative claim has a URL + publication date.
  Anything older than 2024-01 → flag `"legacy": true`. Anything that's
  vendor marketing → must be corroborated by an independent source.
- **Specificity**: "post to LinkedIn" is not an answer. "Post on
  Tuesday at 09:00 ET to LinkedIn with this exact copy, tag @JoeBloggs
  who runs the Mechanical Engineers Network group of 47K members" is.
- **Numbers over adjectives**: "high engagement" → "median 23 comments
  on the 12 top-50 r/SolidWorks posts in Q4 2025"
- **Falsifiability**: every recommendation has a measurable success
  criterion. "Get more stars" is not a criterion. "200 stars in 30
  days from a single HN launch" is.
- **Bias check**: explicitly flag where you're guessing vs citing.
  Mark unverified estimates `[UNVERIFIED — triangulated]`.

---

## 8. What to skip

- Generic startup advice ("build in public", "ship daily"). Assume the
  reader has read every Paul Graham essay.
- Lists of CAD vendors and their feature matrices. We have those.
- Re-litigating the architecture decisions in section 2.
- ML / LLM-architecture research. We are not training models.
- Anything older than 2024 unless it's a foundational standards
  document (ISO, ASME, ASQ).

---

## 9. Tone

Write like a senior engineering manager who has shipped twice as a
solo dev, runs an engineering team now, and has 30 minutes to decide
where the next quarter goes. No hedge sentences. No "it depends".
Recommend. Cite. Move.

---

## 10. STOP gate

When the five files are written and citations cross-check, print:

```
RESEARCH_COMPLETE
```

Nothing else after that line.
