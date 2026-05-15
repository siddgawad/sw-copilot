# SW Copilot — Demo Script

## For LinkedIn / Screen Recording

This script gives you a tight 2-minute demo that hits the three most impressive moments.

---

## Setup (before recording)

1. Open SolidWorks 2021
2. Start SW Copilot backend (auto-starts when SolidWorks loads the add-in)
3. Create a **New Part** — File → New → Part → OK
4. The chat panel is on the right

---

## Demo Sequence

### Act 1 — Instant part creation (30 seconds)

Type exactly:
```
create a 50mm wide 30mm deep 20mm tall box
```
*Watch: the part appears. No clicking, no menus.*

Then:
```
add four M6 counterbore holes at the corners
```
*Watch: four holes appear with ISO-correct dimensions. Point out: "It looked up M6 counterbore specs from ISO 4762 automatically."*

Then:
```
add a 2mm fillet on all edges
```
*Watch: edges get filleted.*

**Pause here** — zoom in on the model. Let it sit for 2 seconds.

---

### Act 2 — Workflow automation (45 seconds)

Type:
```
set revision to A, drawn by Siddhant, date today
```
*Watch: "Title block updated: Revision=A, DrawnBy=Siddhant, Date=2026-05-15"*

Open **File → Properties** to show the custom properties were actually written.

Then:
```
export this as PDF
```
*(Save the file first if it's unsaved: File → Save As → any name)*

*Watch: "Exported to [path].pdf"*

Open the folder — the PDF is there. Open it. *This proves it's not a preview.*

---

### Act 3 — The closer (15 seconds)

Type:
```
create a 40mm diameter shaft 100mm long
```
*(Open a new part first — File → New → Part)*

*Watch: circular sketch + extrusion. No LLM call — this runs in under 0.1 seconds.*

**Closing line for the video:** *"This is SW Copilot — open source, deterministic, no guessing. Built on ISO lookup tables, not AI memory. Link in bio."*

---

## What to say on LinkedIn

> I built a SolidWorks add-in that takes natural language and executes it directly through the COM API.
>
> No macro files. No generated code. The LLM emits structured JSON; the C# executor runs it deterministically.
>
> It looks up M6 counterbore specs from ISO 4762 tables — not from the model's memory. Dimensions are either from standards tables or explicitly stated.
>
> New: it also handles the boring stuff engineers waste time on — batch exports to PDF/DXF/STEP, title block updates, drawing QA checks.
>
> Open source. Free Groq API key. Works with SolidWorks 2021.
>
> github.com/siddgawad/sw-copilot

---

## Common questions to prepare for

**"Does it work with SolidWorks 2022/2023?"**
→ Tested on 2021. COM API signatures vary between versions — may work, needs testing.

**"Does it send my part to the cloud?"**
→ The chat prompt goes to Groq's API. The part file stays local. The backend runs on your machine.

**"What happens when the AI gets it wrong?"**
→ There's a pre-execution rule engine that rejects geometric impossibilities before any COM call. Standard SolidWorks undo works for individual features.

**"Can it do assemblies?"**
→ Not yet. Parts and drawings today.

**"How is this different from MecAgent?"**
→ MecAgent is $84/mo and cross-CAD. SW Copilot is free, open source, and goes deeper on SolidWorks. The architecture is different — everything is deterministic after the intent step.
