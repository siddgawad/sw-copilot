# Common Mechanical Feature Library — Standard Patterns and Proportions

## Mounting Plates and Base Plates
A mounting plate is a flat rectangular plate with through holes for fastening.
Standard proportions: thickness = 6–20mm; hole inset = 10mm (M6) or 14mm (M8) from edges.
Common sizes: 100×80, 150×100, 200×150, 250×200, 300×250mm (length × width)
Typical material: steel S235/A36 (structural), 6061-T6 aluminium (lightweight)
Standard hole pattern: 4 holes at corners; for plates >200mm add centre row holes at 100–150mm spacing.
Fillet radius: 2mm on all vertical edges for steel, 3mm for aluminium.

## Flanges and Flange Plates
A flange is a circular plate with a central bore and bolt holes on a PCD.
Central bore: sized for the pipe/shaft OD + clearance (H7/h6 fit for precision, H8/f7 general)
Bolt hole count: 4 for DN≤50 pipe; 6 for DN65–150; 8 for DN>150
PCD (bolt circle diameter) rule: PCD ≈ OD_flange × 0.65 to 0.75
Flange OD rule: OD_flange ≈ nominal_bore × 2.0 to 2.5 for low pressure
Flange thickness: typically equal to nominal bolt diameter or 0.15 × OD_flange (whichever larger)
Raised face (RF): 2mm above flange face, diameter = nominal_bore + 20mm

## Shafts and Stepped Shafts
A shaft is a cylinder that transmits torque. Steps down in diameter from drive end to bearing seats.
Minimum shaft diameter for torque T (Nm): d ≥ ∛(16T / (π × τ_allow)) where τ_allow ≈ 40 MPa mild steel
Shoulder height at step: 2–3mm for shaft ≤20mm; 3–5mm for shaft 20–50mm; 5–8mm for shaft >50mm
Shoulder fillet: r = 0.5–1.0mm at each step (stress relief)
Keyway width: DIN 6885 — 6mm shaft → 2mm key; 8mm → 3mm; 10mm → 4mm; 12mm → 5mm; 17mm → 6mm; 22mm → 8mm; 30mm → 10mm
Centre drill both ends for turning operations.

## Brackets (L-Bracket, Right-Angle Bracket)
An L-bracket connects two perpendicular surfaces.
Base flange: mounting holes as per base material fastener size (usually 2–4 holes)
Vertical flange: matches load attachment (2–4 holes)
Material thickness: 3–5mm steel, 5–8mm aluminium, for general load brackets
Gusset: triangular reinforcement at the inside corner; height = 50–70% of shorter leg
Gusset thickness = same as flange thickness

## Bearing Housings (Pillow Block Style)
Bore size: standard sizes match bearing OD: 30, 35, 40, 47, 52, 62, 72, 80, 90, 100mm
Housing wall thickness: minimum 8mm for bore ≤30mm; 10mm for ≤60mm; 15mm for >60mm
Bolt holes: 2 (inline) for pillow block; 4 (flanged) for plummer block
Mounting PCD: ≈ bore_diameter + 2 × (wall_thickness + hole_clearance)

## Gears (Spur Gear Basics)
Module (m): controls tooth size. m = pitch_diameter / number_of_teeth
Common modules: 1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10mm
Addendum (tooth height above PCD): 1.0 × m
Dedendum (tooth depth below PCD): 1.25 × m
Tooth depth total: 2.25 × m
Face width: 8–12 × module (standard); max 14 × module
Centre distance: (z1 + z2) × m / 2 where z1, z2 = tooth counts

## Springs (Compression Spring Basics)
Wire diameter d, coil diameter D, free length L0, active coils n
Spring rate k = (G × d^4) / (8 × D^3 × n) where G = 80000 N/mm² (steel)
Typical spring index: C = D/d = 6–12 (preferred 8–10)
Slenderness ratio: L0/D < 4 to avoid buckling without guide
Solid height Ls = n × d (compressed to solid)
