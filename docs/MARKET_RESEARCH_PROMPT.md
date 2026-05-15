# SW Copilot — Deep Research Prompt for GPT (Deep Research / Browsing Mode)

> **Instructions for use:** Paste the section below the horizontal rule into ChatGPT with Deep Research enabled,
> or into Gemini Deep Research. Ask it to return results as a structured markdown file called
> `SW_COPILOT_MARKET_RESEARCH.md`. The output will feed directly into the engineering roadmap.

---

## CONTEXT: WHAT WE'RE BUILDING

We are building **SW Copilot** — an AI-powered SolidWorks add-in that converts natural language into
deterministic SolidWorks part geometry. The system works as follows:

```
User types: "make a 120x80x10mm base plate with four M6 counterbore holes at the corners"
     ↓
Python backend: parses intent → injects ISO standard dimensions → emits OperationGraph JSON
     ↓
C# add-in: executes deterministic SolidWorks COM API calls → creates parametric feature tree
     ↓
Validation: compares requested geometry to actual PartReport → reports pass/fail
```

Key differentiators we believe we have:
- No macro injection, no eval, no script execution — pure structured JSON → COM calls
- ISO standards dimensions come from hardcoded lookup tables (not LLM memory)
- Pre-execution geometric rule engine rejects impossibilities before any COM call
- Supports SolidWorks 2021 natively as a .NET 4.8 COM add-in
- Currently free and open-source (MIT)

**Our north star competitor is MecAgent.** We need to understand exactly what MecAgent does,
where it excels, where it falls short, and what it would take to match or surpass it.

---

## RESEARCH TASKS — Return all findings in `SW_COPILOT_MARKET_RESEARCH.md`

---

### SECTION 1: MecAgent Deep Dive

MecAgent is an AI agent for mechanical engineering / CAD automation.
Research everything publicly available about it.

1. **What is MecAgent exactly?**
   - Who built it (company, academic lab, or individual)?
   - What CAD tools does it support (SolidWorks, Fusion 360, CATIA, FreeCAD, OpenSCAD)?
   - What is the underlying approach — does it generate macros, call COM APIs, use an intermediate IR, or something else?
   - Is it cloud-hosted, locally installed, or a browser extension?

2. **Capability inventory — what can MecAgent actually do?**
   List every confirmed feature with evidence (demo video, paper, product page, GitHub):
   - What part types can it create from natural language?
   - Can it modify existing parts or only create from scratch?
   - Does it support assemblies?
   - Does it validate geometry post-execution?
   - Does it use standards data (ISO, ASME, DIN) or freeform dimensions?
   - Does it support multi-turn conversations (follow-up commands)?
   - Does it generate fully-defined sketches with driving dimensions?
   - Can it handle units (mm, inch, metric/imperial)?

3. **MecAgent failure modes — what does it get wrong?**
   From demos, papers, GitHub issues, Reddit, Twitter/X, YouTube comments:
   - What prompts cause it to hallucinate dimensions?
   - What operations fail most often?
   - How does it handle ambiguous prompts?
   - What is its accuracy rate on published benchmarks (if any)?

4. **MecAgent business model:**
   - Free, freemium, paid subscription, or enterprise only?
   - Pricing (if known)?
   - Is there a public API?
   - GitHub stars / user adoption signals?

---

### SECTION 2: Full Competitive Landscape — CAD AI Tools

Research ALL publicly available AI-assisted CAD tools as of 2026. For each tool, report:
- Tool name and maker
- CAD platforms supported
- Approach (natural language, sketch recognition, generative, topology optimization, etc.)
- Pricing model
- GitHub stars (if open source)
- Key strength
- Biggest weakness or gap
- Whether it targets individual designers, teams, or enterprise

**Tools to research (at minimum — add any others you find):**
- MecAgent
- Autodesk AI (any Fusion 360 / AutoCAD AI features)
- Onshape AI (PTC)
- SolidWorks Copilot (Dassault Systèmes official — if it exists)
- CADFUSION AI or similar
- Text2CAD (any academic papers or open-source projects)
- CADmium (browser-based CAD with AI)
- SketchUp AI features
- Plasticity (any AI?)
- Zoo / KittyCAD (API-first CAD, ML team)
- Any NVIDIA NIM or Isaac Sim integrations with CAD
- Any open-source projects on GitHub tagged `cad` + `llm` or `cad` + `ai`
- Academic papers on "natural language to CAD" — list the top 5 by citation count

Produce a **comparison table** with columns:
`Tool | Platform | Approach | Price | SW Support | Standards Data | Validation | Open Source`

---

### SECTION 3: What Mechanical Engineers Actually Need

Research forums, communities, and surveys to understand real user pain points.

**Sources to check:**
- r/SolidWorks, r/CAD, r/engineering, r/mechanical_engineering on Reddit
- SolidWorks forums (forum.solidworks.com)
- GrabCAD community discussions
- LinkedIn posts and articles from mechanical engineers
- YouTube comments on SolidWorks tutorial videos
- Any published surveys on CAD productivity or AI adoption in engineering

**Answer these questions:**
1. What are the top 5 most tedious tasks in SolidWorks that engineers would love to automate?
2. What is the #1 most common type of part that engineers create repeatedly (brackets, plates, shafts, housings)?
3. How much time do engineers spend on standard/repeated features vs novel design work?
4. What are the most common mistakes engineers make that cost rework time?
5. What do engineers say when asked about AI in CAD — excited, skeptical, or already using tools?
6. What is the biggest concern engineers have about AI-generated geometry (accuracy, standards compliance, audit trail)?
7. Do engineers care about ISO/ASME standards compliance in AI outputs, or just "looks right" geometry?
8. What SolidWorks feature types are most commonly created in mechanical design shops?
   Rank by usage: sketches, extrudes, fillets, holes, patterns, assemblies, drawings, sheet metal, surfaces

---

### SECTION 4: SolidWorks Ecosystem and Market Size

1. **How many SolidWorks seats are installed worldwide?** (Dassault official figures or analyst estimates)
2. **What is the breakdown by industry?** (aerospace, automotive, consumer products, medical, industrial machinery)
3. **What is the average salary of a SolidWorks user?** (mechanical engineer, CAD designer, drafter)
4. **What is the SolidWorks add-in ecosystem like?**
   - How many add-ins exist on the SolidWorks marketplace?
   - What are the top-selling add-ins and their price points?
   - What categories of add-ins sell best (CAM, simulation, PDM, productivity, generative)?
   - Is there precedent for a subscription-priced AI add-in?
5. **What are the SolidWorks certification / partner programs?**
   - What does it cost and how long does it take to become a certified SolidWorks add-in?
   - What is the SolidWorks marketplace revenue share?
6. **Threat: Is Dassault building this themselves?**
   - Does SolidWorks have any official AI/natural-language feature roadmap?
   - What has Dassault announced at SolidWorks World 2024/2025?
   - Is there a "SolidWorks Copilot" product in development?

---

### SECTION 5: Technical Benchmark — What "As Good As MecAgent" Requires

Based on your research, define a concrete technical benchmark:

1. **Prompt coverage:** What is the minimum set of prompt types an AI CAD tool must handle to be considered production-grade? (List 20–30 canonical test prompts.)

2. **Accuracy standard:** What accuracy rate on geometry (correct dimensions, correct feature count, correct topology) is acceptable for engineering use vs. just demos?

3. **Speed standard:** What response time (prompt → part visible in viewport) is acceptable for professional use?

4. **Standards compliance:** Which ISO/ASME standards are most important to get right for mechanical design in North America and Europe?

5. **Feature completeness checklist:** What is the minimum feature set to be taken seriously as a professional tool?
   - Which SolidWorks operations must be supported (rank by importance)?
   - Assembly support: required or optional for v1?
   - Drawing generation: required or optional for v1?
   - Sheet metal: required or optional for v1?
   - FEA integration: required or optional for v1?

6. **Reliability requirements:** What failure modes are acceptable vs. must never happen?
   - Hallucinated dimensions: acceptable with warning, or never?
   - Wrong hole size: acceptable, or hard failure?
   - Feature that crashes SolidWorks: acceptable, or instant dealbreaker?

---

### SECTION 6: Distribution and Go-To-Market

1. **How do mechanical engineers discover new CAD tools?**
   - SolidWorks App Store vs GitHub vs LinkedIn vs YouTube vs word-of-mouth?
   - Which YouTube channels have the most SolidWorks engineering subscribers?
   - Which LinkedIn communities are most active for SolidWorks users?

2. **What is the best pricing model for a professional SolidWorks AI add-in?**
   - One-time license vs monthly subscription vs per-seat vs per-company?
   - What price points do existing premium SolidWorks add-ins use?
   - Is there a free tier that makes sense (limited operations/month, no standards data)?
   - What do engineers say on Reddit about paying for productivity tools?

3. **What marketing messages resonate with mechanical engineers?**
   - Do they respond to "AI" branding or is it a red flag for professional engineers?
   - Is "standards-grounded" or "deterministic" a selling point or jargon?
   - What do the most successful SolidWorks YouTubers emphasize (speed, accuracy, certification)?

4. **Open-source strategy:**
   - Is there precedent for open-source CAD tools that successfully monetized?
   - Would open-sourcing the backend (Python) but keeping the add-in closed make sense?
   - What do engineers think about contributing to open-source CAD tools?

---

### SECTION 7: Academic and Research Landscape

1. List the top 5 academic papers on "natural language to CAD" or "LLM-driven CAD automation" published 2022–2026.
   For each: authors, venue, approach, accuracy on benchmark, available code.

2. Are there any public datasets for CAD prompt → geometry pairs we can use for evaluation?
   - ABC Dataset (CAD primitives)
   - DeepCAD
   - Fusion 360 Gallery Dataset
   - Any SolidWorks-specific datasets?

3. What benchmarks exist for evaluating CAD AI tools?
   - Is there a standard test set for "natural language to CAD" accuracy?
   - What metrics are used (IoU, feature count match, dimension error %)?

4. Which research groups are most active in this space?
   - MIT, Carnegie Mellon, Stanford, ETH Zurich, or industry labs (NVIDIA, Autodesk Research)?

---

### SECTION 8: Recommended Roadmap

Based on all research above, produce a prioritized recommendation:

1. **Top 3 things SW Copilot must do to match MecAgent** (with specific technical requirements)
2. **Top 3 gaps in the current market that SW Copilot could own** (underserved user need + why no one has filled it)
3. **The single most important prompt type to nail first** (highest frequency + highest impact for engineers)
4. **Recommended v1 feature set** — what to include, what to explicitly cut
5. **Recommended pricing model** with specific price point
6. **Top 3 distribution channels** ranked by expected ROI
7. **Biggest technical risk** that could kill the project

---

## DELIVERABLE FORMAT

Return all findings as a single markdown file `SW_COPILOT_MARKET_RESEARCH.md` with:
- One H2 section per research section above
- Bullet points for findings, not prose paragraphs
- Comparison tables where applicable (use markdown tables)
- Source citations as inline links or footnotes where possible
- Each section ends with **"Recommended Action:"** — one concrete thing to do based on the findings
- Flag anything you could not verify as **[UNVERIFIED — research manually]**
- Do NOT fabricate ratings, prices, GitHub stars, or user counts — use real data or say unverified

Target length: comprehensive, not padded. Aim for completeness on each question, not word count.
