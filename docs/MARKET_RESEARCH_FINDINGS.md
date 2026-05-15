# SW Copilot — Market Research Findings
**Source:** GPT Deep Research, May 2026
**Brief used:** `docs/MARKET_RESEARCH_PROMPT.md`

---

## The single most important finding

**Do not lead with free-form text-to-CAD.** That is the immature, unproven, skepticism-heavy part
of the field. MecAgent's own team says part generation is "largely limited to very simple geometry."
Autodesk, Onshape, and SketchUp are shipping guided actions and constrained features — not design
autonomy. The gap that engineering communities visibly complain about is repetitive workflow pain,
not "AI that designs for me."

**The commercially proven wedge is workflow automation:**
- Batch exports (revision-aware, DXF/PDF/STEP at once)
- Title block and custom property normalization
- Drawing cleanup (missing dimensions, tolerance omissions, GD&T gaps)
- Standards-aware pre-checks with citations
- Macro generation from constrained natural language templates

---

## MecAgent — what it actually is

| Item | Finding |
|---|---|
| Type | Cross-CAD AI layer (SW, CATIA, Inventor, Fusion, Creo) |
| Real value per community | Macro/automation generation without coding; repetitive edits, exports, drawing cleanup |
| Autonomous part generation | Cautious: "still not as good as we want"; simple geometry only today |
| Pricing | Student $16/mo; Starter/Pro $84/mo; Advanced+ $417/mo; Enterprise custom |
| Enterprise | On-prem/private cloud option; SOC 2 claimed |
| Strategic implication | They are building broad cross-CAD; we can go deeper on SOLIDWORKS specifically |

---

## Competitive pricing anchors

| Tool | Price | Notes |
|---|---|---|
| MecAgent Student | $16/mo (yearly) | Simple SW tasks, text-to-CAD, automations |
| MecAgent Starter/Pro | $84/mo (yearly) | Full feature set |
| MecAgent Advanced+ | $417/mo (yearly) | Enterprise features |
| Autodesk Fusion | CA$79/mo (yearly) | Full CAD suite with AI assistant |
| Onshape Standard | $1,500/user/year | Cloud CAD with AI Advisor |
| SketchUp AI add-on | $11.99/mo + 1,500 credits | Credit-based AI actions |
| Zoo Design Studio | Free tier (20 min reasoning) | AI-native CAD, cloud-dependent |

**Pricing recommendation:** Position SW Copilot at $29–49/mo for individual engineers
(above MecAgent Student, below Starter/Pro) and $149–249/mo for team/seat licenses.
Enterprise: custom, with on-prem deployment option as the gate-opener.

---

## Market size

- **8.5 million** SOLIDWORKS users
- **400,000** companies
- **110** countries
- **400+** solution partners
- Large enough for a focused add-in business at any reasonable conversion rate

---

## Standards that must be in the corpus (Phase 1)

| Domain | Standard | Priority |
|---|---|---|
| GD&T and drawings | ASME Y14.5, ASME Y14.100 | P0 |
| Inch threads | ASME B1.1 | P0 |
| Inch fasteners | ASME B18.2.1, ASME B18.3 | P0 |
| Metric threads | ISO 965-1:2026 | P0 |
| Metric fits | ISO 286-1 | P0 |
| Metric clearance holes | ISO 273 | P0 (already in dimension_resolver.py) |
| General tolerances | ISO 2768-1, ISO 2768-2 | P1 |
| Metric fasteners | ISO 4762, ISO 10642, ISO 4042 | P1 (ISO 4762 already done) |

---

## Biggest risks

| Risk | Mitigation |
|---|---|
| Selling "AI designs parts for you" — trust collapse when it fails | Sell time saved on boring work; always show dry-run preview |
| CAD IP leakage through prompts or uploads | Local-first; no file upload to cloud by default; audit log |
| SOLIDWORKS native AI (Dassault) crowding the space | Go deeper on WORKFLOW automation; they will ship generic chat |
| Partner/marketplace economics unknown | Validate direct sales first; avoid marketplace rev-share dependency |
| Standards corpus licensing | Use customer-supplied standards libraries or licensed copies only |

---

## What this means for our architecture

Our `OperationGraph → COM executor` is the RIGHT engine — we just need to point it at
workflow operations, not just part-creation operations.

**Operations to add (missing from current 12-type set):**
- `export_drawing` — batch export to PDF/DXF/STEP with naming rules
- `update_title_block` — set custom properties (revision, drawn by, date, title)
- `check_drawing` — scan for missing tolerances, GD&T callouts, unlinked balloons
- `find_part` — search active vault/directory for similar parts by dimension/feature
- `generate_macro` — emit a SOLIDWORKS macro (.swp/.dll) from natural language description

These five operations, added to the current executor, give us the MecAgent wedge.
