# Mechanical Design Rules and Engineering Best Practices

## Hole and Edge Distance Rules
Minimum hole center-to-edge: 1.5× clearance hole diameter (ferrous metals)
Standard/recommended edge inset: 2× clearance hole diameter (general practice)
Minimum hole center-to-center: 3× clearance hole diameter

Edge inset quick reference (standard practice for machined parts):
- M4 holes: 9mm inset from edge
- M5 holes: 10mm inset from edge
- M6 holes: 10mm inset from edge (most common — use this as default)
- M8 holes: 14mm inset from edge
- M10 holes: 16mm inset from edge
- M12 holes: 20mm inset from edge

CORNER HOLE POSITION RULE: For N holes symmetrically at "corners" of a rectangular part of width W and length L centered at origin:
4 corners → positions: (-L/2 + inset, -W/2 + inset), (L/2 - inset, -W/2 + inset), (-L/2 + inset, W/2 - inset), (L/2 - inset, W/2 - inset)

## Wall Thickness Minimums
Steel (machined): 1.5mm minimum structural, 3mm recommended
Aluminium (machined): 2.0mm minimum, 4mm recommended
Steel (sheet metal): 0.8mm to 6mm typical; 1.5mm general purpose
Aluminium (sheet metal): 1.0mm to 4mm typical

## Chamfer and Fillet Rules
Lead-in chamfers for shafts into bearings: 1×45° standard (1mm × 45°)
Fillet radii at shoulders: minimum 0.5mm to prevent stress concentration; standard is r ≥ 0.05× diameter
Undercut for grinding: 0.5mm depth, 2mm width minimum
General part fillets for stress relief: 2–5mm depending on section size
Edge break (cosmetic): 0.2–0.5mm chamfer on all sharp exposed edges

## Thread and Boss Design
Minimum boss height for tapped hole: 2× thread nominal diameter
Boss outer diameter: minimum 2× drill diameter, standard 2.5× drill diameter
For M6 tapped hole: boss OD ≥ 16mm recommended
For M8 tapped hole: boss OD ≥ 20mm recommended
Minimum material below through-hole: 0 (through-hole exits completely)
Minimum material below blind hole: 2 × thread pitch (do not drill into mating surface)

## Bearing Seat Tolerances
Shaft bearing seat (tight fit): k6 tolerance on shaft OD
Housing bore (tight fit): K7 tolerance on bore ID
Typical shaft-bearing interference: 0.005mm to 0.020mm
Shaft shoulder height to retain bearing: equal to inner race width × 0.75

## Surface Finish Guidelines (Ra values)
Ground bearing seat: Ra 0.4–0.8 μm
Turned shaft (general): Ra 1.6–3.2 μm
Milled face (general): Ra 3.2–6.3 μm
Drill hole (general): Ra 6.3–12.5 μm
Sand cast: Ra 12.5–25 μm

## Standard Part Geometry Conventions (SolidWorks)
Origin placement: Centre all symmetric parts at the SolidWorks origin unless assembly context requires otherwise
Extrusion direction: Top Plane parts extrude upward (+Z); Front Plane profiles extrude along +Y; Right Plane profiles extrude along +X
Shaft axis: shafts and cylinders sketch on Front Plane, extrude_boss along Y (depth_mm = shaft length)
Plate axis: plates sketch on Top Plane, extrude_boss along Z (depth_mm = plate thickness)
Flange base: sketch on Top Plane, extrude_boss for flange thickness; bolt holes on "flange_feature top" face
