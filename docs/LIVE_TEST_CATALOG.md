# Live Test Catalog — Every Supported Prompt

Copy any prompt below into the SW Copilot task pane after closing/restarting
SolidWorks and the backend. Each one **routes through a deterministic
pattern with zero LLM calls** (verified by 91 automated tests in
`tests/test_feature_matrix.py`).

After running, paste the resulting Runtime output and ✅/❌ status below
each prompt block.

---

## 1. Box / Block (`box_v0`)

```
create a 50mm wide 30mm deep 20mm tall box
100x60x40mm block
create a 200mm x 150mm x 25mm box
box 80 by 40 by 20
create a 1000mm by 800mm by 50mm rectangular block
tiny box 5mm x 5mm x 5mm
```

Expected: sketch on Front Plane → rectangle → extrude → rebuild.

---

## 2. Plate (`plate_v0`)

```
create a 100x100x5mm plate
make a plate 200mm x 150mm x 6mm
plate 100 by 60 by 5
mounting plate 80x60x4mm
base plate 300x200x10mm
create a plate 100x100x5mm on front plane
mounting plate 80x60x4mm with 4 M5 holes at corners
plate 120x80x6mm with 4 M8 counterbored holes at corners
create a 100x60x10mm plate with 4 M6 holes at corners and 2mm fillet on all edges
create a 120x80x6mm plate with 4 M5 counterbored holes at corners and 3mm fillet on all edges and 1mm chamfer on top edges
```

Expected: smallest dimension becomes thickness; corner holes use ISO 273
clearance; compound prompts produce a single graph with all features.

---

## 3. Flange (`flange_v0`)

```
create a flange 100mm OD 6mm thick
flange 80mm diameter 5mm thick
disc 50mm diameter 3mm thick
flange 100mm OD 6mm thick with 6 M8 holes on 80mm PCD
flange 200mm OD 10mm thick with 8 M10 holes on 160mm PCD
flange 150mm OD 8mm thick with 6 M8 holes on 120mm PCD and 2mm fillet on all edges
```

Expected: Front Plane circle → extrude → seed hole at (PCD/2, 0) →
circular_pattern → rebuild.

---

## 4. Cylinder (`cylinder_v0`)

```
create a cylinder 40mm diameter 100mm long
create a cylinder 50mm diameter 200mm long
cylinder 30mm diameter 75mm long
```

---

## 5. Shaft (`shaft` — flanged-shaft template)

```
make a 30mm diameter shaft 150mm long
```

Expected: emits a flange + shaft pair (this is the canonical "engineering
shaft" — bare shaft + collar flange at the base).

---

## 6. Gear (`gear`)

```
gear 40mm pitch diameter 20 teeth
gear module 2 with 24 teeth
```

---

## 7. L-Bracket / Angle Bracket (`bracket_v0`)

```
create an L-bracket 80x60x5mm
make a bracket 100x80x6mm
L-bracket 120x80x8mm
angle bracket 60x40x4mm
```

Expected: two perpendicular plates (Top Plane horizontal + Front Plane
vertical), each sharing the bracket thickness.

---

## 8. Bushing (`bushing_v0`)

```
create a bushing 30mm OD 15mm ID 40mm long
bushing 25mm outer 12mm inner 30mm long
make a bushing 40mm OD 20mm ID 50mm long
```

Expected: outer cylinder extrude → inner cut through.

---

## 9. Spacer — round or square (`spacer_v0`)

```
create a spacer 30mm OD 10mm ID 5mm thick
round spacer 25mm OD 8mm ID 5mm thick
rectangular spacer 40x20mm 10mm bore 5mm thick
```

---

## 10. Pipe / Tube (`pipe_v0`)

```
create a pipe 25mm OD 20mm ID 200mm long
tube 32mm OD 28mm ID 500mm long
pipe 30mm OD 2mm wall 250mm long
```

Expected: long hollow cylinder. Pipe with `Nmm wall` notation auto-computes
ID = OD − 2·wall.

---

## 11. Enclosure / Housing / Junction Box (`enclosure_v0`)

```
create an enclosure 100x60x40mm with 2mm walls
make a housing 200x150x80mm 3mm wall thickness
junction box 80x80x40mm 2mm walls with 4 M3 mounting holes at corners
instrument case 150x100x50mm 2mm walls
create an enclosure 120x80x50mm with 3mm walls and 2mm fillet on all edges
create a junction box 80x80x40mm 2mm walls with 4 M3 holes at corners and 2mm fillet on all edges
```

Expected: box → shell (removes top face) → corner mounting holes → optional
fillet/chamfer → rebuild. The complete enclosure recipe in one prompt.

---

## 12. Washer ISO 7089 (`washer_v0`)

```
create an M3 washer
M4 washer ISO 7089
M5 washer
create an M6 washer
M8 washer
M10 plain washer
M12 washer
M16 washer
M20 washer
make a washer 10mm OD 4mm ID 1mm thick
```

Expected: ISO 7089 dimensions automatically: M3→Ø7/3.2/0.5mm, M6→Ø12/6.4/1.6mm,
M10→Ø20/10.5/2mm, etc.

---

## 13. Follow-up features on an active part

After creating ANY part above, these prompts modify it in-place:

```
add four M6 counterbore holes at the corners
add four M8 counterbore holes at the corners
add four M5 holes at the corners
add a 2mm fillet on all edges
add a 5mm fillet on all edges
add a 10mm fillet on all edges
add a 2mm chamfer on the top edges
add a 3mm chamfer on the top edges
```

These read the active part's bounding box from the live SW document — no
need to restate the part dimensions.

---

## 14. Help / capabilities

```
hi
hello
hey
help
what can you do
what are your capabilities
getting started
```

Returns a `noop` listing available operations — no LLM call.

---

## 15. Coverage proof

Run all 91 automated tests with:

```powershell
cd C:\Projects\sw-copilot\agent-backend
.\.venv\Scripts\python.exe -m pytest tests/test_feature_matrix.py -v
```

Expected: `91 passed in <1 second`. Every prompt above is exercised at the
schema level. Live SolidWorks rendering still needs you to actually run
them in SW — paste results below each section.

---

## 16. LLM-disabled smoke test

To prove the entire app works without ANY LLM:

```
# In agent-backend/.env:
LLM_DISABLED=true

# Restart backend
cd C:\Projects\sw-copilot
.\Start-Backend.ps1
```

Now run any prompt above. All should still work. Anything NOT in this
catalog will return a clean noop explaining what's supported.

---

## Coverage stats (this session)

| Layer | Patterns | Coverage |
|---|---|---|
| Shape primitives | 12 | box, plate, flange, cylinder, shaft, gear, bracket, bushing, spacer, pipe, enclosure, washer |
| Follow-up features | 3 | corner_holes, fillet, chamfer (top-edges + all-edges) |
| Compound (single-prompt) | All shape patterns + fillet/chamfer | Plate + flange + spacer + pipe + enclosure |
| Standards integrated | ISO 273 (clearance), ISO 4762 (counterbore), ISO 7089 (washers) | Yes |
| Test cases | 91 | All passing |
| LLM-free mode | Yes | `LLM_DISABLED=true` |
| Quota-bypass fallback | Yes | Always-on Ollama local |
