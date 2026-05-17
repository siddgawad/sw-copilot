# Deterministic Natural-Language Compiler

SW Copilot's pattern router is a **deterministic compiler** that turns
common engineering requests into validated SolidWorks operation graphs
**without ever calling an LLM**. Set `LLM_DISABLED=true` in `.env` to run
the app in pure-compiler mode.

This doc is the grammar reference: what English maps to what features,
with the exact regular expressions that recognise each pattern.

---

## What the compiler handles end-to-end (no LLM)

| Category | Pattern | Status |
|---|---|---|
| Greeting / help | "hi", "help", "what can you do" | ✅ |
| Box / block | `WxDxH mm box`, `W mm wide D mm deep H mm tall box` | ✅ |
| Plate (flat) | `WxDxT mm plate`, `mounting plate WxDxT` | ✅ |
| Plate + corner holes | `plate 100x60x5mm with 4 M6 holes at corners` | ✅ |
| Plate + counterbores | `plate 120x80x6mm with 4 M8 counterbored holes at corners` | ✅ |
| Flange (disk) | `flange ODmm thick T mm`, `disc 80mm dia 5mm thick` | ✅ |
| Flange + bolt circle | `flange 100mm OD 6mm thick with 6 M8 holes on 80mm PCD` | ✅ |
| Cylinder | `cylinder Dmm diameter Lmm long` | ✅ |
| Shaft (with flange) | `30mm diameter shaft 150mm long` | ✅ |
| Gear | `gear 40mm pitch diameter 20 teeth` | ✅ |
| Corner holes on active part | `add four M6 counterbore holes at the corners` | ✅ |
| Top-edge chamfer on active part | `add a 3mm chamfer on the top edges` | ✅ |
| All-edge fillet on active part | `add a 5mm fillet on all edges` | ✅ |

The above are **proven by automated tests** (`tests/test_feature_matrix.py`, 51 cases).

---

## Test coverage matrix

`tests/test_feature_matrix.py` runs:
- Box at 6 scales (5×5×5 mm up to 1000×800×50 mm)
- Plate with 5 dimension formats
- Plate with corner holes (M5, M6, M8, M10)
- Plate with counterbore corner holes
- Plate with explicit plane hints (Top / Front / Right)
- Flange at multiple scales
- Flange + 4/6/8-hole bolt circles on various PCDs
- Cylinder at 3 scales
- Shaft pattern recognition
- Follow-up: 4 fastener sizes × 4 hole types × bbox-aware
- Follow-up: all-edge fillet at R2 / R5 / R10
- Follow-up: top-edge chamfer at 2mm / 3mm
- Full sequence: plate → corner holes → fillet
- Single-prompt compound: `flange 150mm OD 8mm with 6 M8 counterbored holes on 120mm PCD`
- Schema round-trip through Pydantic (JSON → object → JSON)
- Schema version guard (every graph must emit `schema_version: "0.2"`)

Run it any time with:
```powershell
cd agent-backend
.\.venv\Scripts\python.exe -m pytest tests/test_feature_matrix.py -v
```

---

## Grammar reference (regex-level)

### Box / block

Keywords: `box`, `block`, `cube`, `rectangular block`

Recognised dimension formats:
- `WxHxD mm` — `100x60x40mm block`
- `W mm x H mm x D mm` — `create a 50mm x 40mm x 30mm box`
- `W by H by D` — `50 by 30 by 20 rectangular block`
- `W mm wide H mm deep D mm tall` — `50mm wide 30mm deep 20mm tall box`

Axes: sketch on **Front Plane**, dims map x/y/z = wide/deep/tall.

### Plate

Keywords: `plate`, `mounting plate`, `base plate`, `flat plate`

Recognised forms:
- `100x60x5mm plate`
- `plate 200 by 150 by 6mm`
- `mounting plate 80x60mm 4mm thick`

The **smallest dimension is always the thickness** (extrude depth). The
two larger dimensions are the in-plane size.

Optional features in the same prompt:
- `… with 4 M5 holes at corners` — adds clearance through-holes
- `… with 4 M8 counterbored holes at corners` — adds counterbore
- `… on top plane` / `front plane` / `right plane` — override sketch plane

### Flange

Keywords: `flange`, `disc`, `disk`, `round plate`, `circular flange`

Recognised forms:
- `flange 100mm OD 6mm thick`
- `flange 80mm diameter 5mm thick`
- `disc 120mm 8mm thick` (first/larger dim = OD, smaller = thickness)

Optional bolt circle:
- `… with 4 M6 holes on 60mm PCD`
- `… with 6 M8 counterbored holes on 90mm pitch circle`
- `… with 8 M10 holes on 160mm BCD`

Emits: sketch (circle) → extrude → hole at (PCD/2, 0) → circular_pattern.

### Cylinder / shaft

- `cylinder 40mm diameter 100mm long`
- `cylinder 50mm OD 200mm long`
- `30mm shaft 150mm long`  → routes to flanged-shaft template

### Follow-up features (require an active part)

The follow-up handler reads `bounding_box_mm` from the active part:

- `add four M{n} counterbore holes at the corners` — n ∈ {3,4,5,6,8,10,12}
- `add four M{n} holes at the corners` — clearance through
- `add a {R}mm fillet on all edges` — fillet uses `IsLine` + Mark=1
- `add a {D}mm chamfer on the top edges` — selects only top face edges

### Greeting / help

Keywords: `hi`, `hello`, `hey`, `help`, `what can you do`, `getting started`

Returns a `noop` listing the available operations.

---

## How to extend the compiler (add a new pattern)

1. Create `agent-backend/patterns/<your_pattern>.py`:
   ```python
   import re
   from typing import Optional
   from models.schemas import OperationGraph

   _KEYWORD = re.compile(r"\b(bracket|angle\s+bracket)\b", re.IGNORECASE)
   _DIMS    = re.compile(r"(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)\s*mm")

   def try_generate(prompt: str) -> Optional[OperationGraph]:
       if not _KEYWORD.search(prompt):
           return None
       m = _DIMS.search(prompt)
       if not m:
           return None
       a, b, c = float(m.group(1)), float(m.group(2)), float(m.group(3))
       return OperationGraph(
           schema_version="0.2",
           part_family="bracket_v0",
           part_name="bracket",
           operations=[
               # ... emit sketch + extrude + holes
           ],
       )
   ```

2. Register it in `agent-backend/patterns/router.py`:
   ```python
   from patterns.bracket import try_generate as try_generate_bracket
   ...
   _HANDLERS = [
       try_generate_help,
       try_generate_gear,
       try_generate_flange,
       try_generate_plate,
       try_generate_bracket,   # add here
       ...
   ]
   ```

3. Add test cases in `tests/test_feature_matrix.py`:
   ```python
   @pytest.mark.parametrize("prompt,expected_dims", [
       ("L-bracket 80x60x5mm", (80, 60, 5)),
       ("angle bracket 100x100x6mm", (100, 100, 6)),
   ])
   def test_bracket_at_scales(prompt, expected_dims):
       graph = _run(prompt)
       assert graph is not None
       assert graph.part_family == "bracket_v0"
   ```

4. Run `pytest tests/test_feature_matrix.py` — green = ready.

5. If the new pattern overlaps with `followup_features`, add its keyword to
   `_NEW_SHAPE_KEYWORDS` in `patterns/followup_features.py` so single-prompt
   compound requests route to the shape pattern, not the followup handler.

---

## LLM-disabled mode

Set `LLM_DISABLED=true` in `agent-backend/.env`. The app will:
- Run every pattern in the router
- If no pattern matches, return a clean `noop` listing supported patterns
- Never call Gemini / Groq / Ollama
- Never burn quota

This is the recommended setting for users who:
- Don't trust any LLM
- Want strictly deterministic behaviour
- Are offline / air-gapped
- Are demoing the app to skeptical engineers

The deterministic compiler covers the **most common 80% of engineering
requests** today (box, plate, flange, cylinder, shaft, gear, plus the
top-3 follow-up edits: holes, fillet, chamfer). Adding new patterns is
mechanical — see "How to extend" above.
