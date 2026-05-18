# VALUE_EVIDENCE.md

Evidence for the economic value of a deterministic "NL → OperationGraph
→ COM" SolidWorks add-in. Each claim tagged `[Snn]`; full citations in
`RESEARCH_SOURCES.json`.

---

## Engineering time wasted on routine CAD work

- Mechanical engineers spend **~33% of their time on non-value-added work**, and **~20% working from outdated information** (Tech-Clarity survey, n=228 manufacturers) `[S01]`.
- An average **15% of engineering time** is lost to non-value-added data management — finding, recreating, translating CAD/PDM data `[S01]`.
- Triangulated estimate: a SOLIDWORKS designer working on plates, brackets and flanges spends **20–35% of modelling time** on repetitive parametric work (corner holes, fastener call-outs, fillets); triangulated from `[S01][S07][S04]`.
- Time-and-motion data for ISO 273/4762 hole call-out lookups not in the literature `[UNVERIFIED]`; triangulated estimate **2–5 min × ~30 holes/plate ≈ 1–2.5 hr/plate** on fastener metadata alone, from `[S01][S04]`.

## Cost of drawing errors and ECOs

- A single Engineering Change Order costs **~US $10,000 routine to several US $100,000s late-stage** (INSEAD case-study aggregation) `[S02]`.
- Projects that incurred engineering changes overran final cost by **72%**, versus **11%** for projects without changes (AFIT/ASEE peer-reviewed regression) `[S03]`.
- Teradyne's Teamcenter rollout cut ECO cycle by **84%** and saved **US $2M/year** `[S08]` (vendor case, flagged).
- **Total Cost of Poor Quality (COPQ)** typically runs **10–30% of annual revenue**; **scrap and rework alone ≈ 2.2% of revenue** at average manufacturers; world-class is <0.6% (ASQ benchmarking) `[S05]`.
- Correct GD&T on circular features widens the acceptance zone by **57%** — directly cutting false-reject scrap on hole-pattern parts `[S06]`.

## SOLIDWORKS-specific market base

- SOLIDWORKS has **>8 million users worldwide**, **~1.5 million commercial seats**, **~285,000 commercial customers** (Dassault Systèmes 2024 Universal Registration Document) `[S10]`.
- **44% of all new MCAD seats sold worldwide in 2024 were SOLIDWORKS** (~42% market share by seat) `[S10]`.
- AI-generated SOLIDWORKS macros pass on **~30% of first attempts**; supplying the type-library signatures raises success to **>80%** — exactly the determinism gap that injected ISO standards + structured op graphs close `[S26]`.

## Industry appetite for AI-assisted CAD (2025 survey data)

- Capvidia/DEVELOP3D survey of 250 US/EU engineering leaders, Aug 2025: **73% of drawing reviews could be automated**; **96% plan to adopt AI 2D review within 1–2 years**; only **55% of company standards are documented, current, and frequently used** `[S29]`.
- Engineers explicitly want **editable parametric output**, not opaque mesh blobs (DEVELOP3D coverage of Autodesk AI announcements) `[S32]`.
- 3DEXPERIENCE World 2026 demos that resonated were live, parametric, and standards-grounded — wind-loaded tank-frame, reverse-engineered drawings — and "minutes" was the headline number `[S31]`.

## Competitive pricing — the market is real and paying

- Zoo.dev Text-to-CAD charges **US $0.50/min ($0.0083/sec)**, billing switched to per-second on **Oct 14 2025**; 40 free minutes/month then paid `[S12][S15]`. Typical generation **$0.08–$0.25/prompt** `[S12]`. A real paying market exists today.
- Zoo's open-source surface is **only the UI** (`KittyCAD/text-to-cad-ui`, 276 stars, **archived Jan 2026**); the model and KCL backend stay closed `[S16]`.
- Documented Zoo limitation: "works best with single objects, not complicated groupings of parts" `[S17]`.

## Why incumbents do not (yet) serve the SOLIDWORKS 2021 desktop base

- Project Bernini → **Neural CAD** is still research; **no commercial NL→parametric CAD product** from Autodesk `[S18]`. Their *Autodesk Assistant* is a support chatbot, not a geometry generator `[S19]`.
- Fusion MCP servers (2025–2026) **validate the LLM-frontend / deterministic-backend architecture** sw-copilot uses `[S20]`.
- Onshape AI Advisor (Oct 2025) and Creo 12 (Jun 2025) added **advisor chatbots and thermal generative design** — not NL→CAD `[S21][S22]`.
- 3DEXPERIENCE LEO / MARIE / AURA "Virtual Companions" launch **mid-2026 onwards, cloud-only** — the entire **SOLIDWORKS 2021 desktop install base is unserved** `[S27][S28]`.
- Public open-weight model for parametric MCAD does **not exist**: CAD-MLLM released only eval code and dataset `[S23]`; BlenderLLM targets Blender Python, not parametric CAD `[S24]`; Seek-CAD/STEP-LLM remain academic `[S25]`.

## Bottom line

A free, deterministic, ISO-grounded, desktop-SOLIDWORKS-2021 NL→CAD add-in
faces a market where (a) addressable base is 8M+ users `[S10]`, (b) engineers waste
20–35% of modelling time on patterns the tool automates `[S01]`,
(c) every published competitor is paid+cloud `[S12]`, a chatbot `[S19][S21]`,
or unreleased `[S27][S30]`, and (d) 96% of surveyed leaders plan to adopt
AI-assisted CAD review within two years `[S29]`. The credibility-by-shipping
window is open through mid-to-late 2026.
