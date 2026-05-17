# SolidWorks Feature Catalog

A comprehensive reference for every major SolidWorks 2021 feature this app can
or should support. Each entry includes the required sketch type, the engineering
purpose, the COM API method, and current implementation status.

Use this catalog as the source of truth when the planner decides which operation
to emit. It is ingested into the RAG vector store at startup and surfaces in the
LLM's context whenever the user requests a feature the deterministic pattern
router does not recognise.

---

## 1. Sketch Type → Feature Compatibility Matrix

A SolidWorks feature is determined by **what kind of sketch profile feeds it**.
Get the sketch wrong and the feature fails to compute.

| Sketch type            | Required closure       | Features that consume it                                                |
|------------------------|------------------------|-------------------------------------------------------------------------|
| Closed loop, single    | Must be closed         | Extrude Boss, Extrude Cut, Revolve, Sweep profile, Loft section         |
| Closed loop, multiple  | Each must be closed    | Multi-region extrude/cut, Loft section with islands                     |
| Open profile, 1 seg    | Open line or arc       | Rib, Sweep path, Wrap (project onto cylindrical face)                   |
| Open profile, N seg    | Open polyline/spline   | Sweep path, Composite curve                                             |
| Centerline + closed    | Closed + axis line     | Revolve Boss/Cut                                                        |
| 3D sketch              | Spatial geometry       | Sweep path (3D), Loft path, Pipe routing                                |
| Sketch with point      | Single point           | Hole Wizard position, Pattern seed, Reference point                     |

**Rule:** if the user request implies a feature, the planner first picks the
correct sketch type, emits the sketch op (with primitives sized correctly),
then emits the consuming feature op referencing that sketch's id.

---

## 2. Boss / Base Features (additive — add material)

| Feature          | Sketch                    | Purpose                                       | COM API                                   | Status |
|------------------|---------------------------|-----------------------------------------------|-------------------------------------------|--------|
| Extrude Boss    | Closed loop               | Linear extrusion along normal                 | `FeatureExtrusion2`                      | ✅      |
| Revolve Boss    | Closed loop + centerline  | Rotate profile about axis                     | `FeatureRevolve2`                        | ✅      |
| Swept Boss      | Closed profile + open path| Move profile along path                       | `InsertProtrusionSwept4`                  | ✅      |
| Lofted Boss     | 2+ closed profile sketches| Blend between profiles                        | `InsertProtrusionBlend2`                  | ❌      |
| Boundary Boss   | 2 boundary curve sets     | Surface-driven blend                          | `InsertProtrusionBoundary`                | ❌      |
| Thicken         | Surface                   | Add thickness to surface                      | `InsertProtrusionThicken`                 | ❌      |

---

## 3. Cut Features (subtractive — remove material)

| Feature           | Sketch                    | Purpose                              | COM API                          | Status |
|-------------------|---------------------------|--------------------------------------|----------------------------------|--------|
| Extrude Cut      | Closed loop               | Linear cut into body                 | `FeatureCut3`                   | ✅      |
| Revolve Cut      | Closed loop + centerline  | Rotational cut                       | `FeatureRevolveCut2`            | ❌      |
| Swept Cut        | Closed profile + open path| Cut along path                       | `InsertCutSwept4`                | ❌      |
| Lofted Cut       | 2+ closed profiles        | Blended cut                          | `InsertCutBlend`                 | ❌      |
| Hole Wizard      | Point positions on face   | Drilled / counterbored / tapped hole | `FeatureCut3` (fallback)        | ✅      |
| Series of Holes  | Multiple coplanar holes   | Hole row across assembly             | `InsertSeriesHole`               | ❌      |
| Thread          | Cylindrical face          | Helical threading                    | `InsertThread2`                  | ❌      |

---

## 4. Pattern Features (replicate)

| Feature             | Input                     | Purpose                                   | COM API                              | Status |
|---------------------|---------------------------|-------------------------------------------|--------------------------------------|--------|
| Linear Pattern     | Source feature + axis     | Row/array along 1–2 axes                  | `FeatureLinearPattern3`             | ✅      |
| Circular Pattern   | Source + rotation axis    | Bolt circle / spokes                      | `FeatureCircularPattern3`           | ✅      |
| Mirror             | Source + mirror plane     | Mirror about plane                        | `InsertMirrorFeature2`              | ✅      |
| Sketch Driven      | Source + sketch points    | Pattern at arbitrary points               | `InsertSketchDrivenPattern`          | ❌      |
| Curve Driven       | Source + curve            | Distribute along curve                    | `InsertCurveDrivenPattern`           | ❌      |
| Table Driven       | Source + (x,y) table      | Discrete table-defined positions          | `InsertTableDrivenPattern`           | ❌      |
| Fill Pattern       | Source + face + spacing   | Tile face with seed                       | `InsertFillPattern`                  | ❌      |
| Variable Pattern   | Source + control sketch   | Per-instance dimension override           | `InsertVariablePattern`              | ❌      |

---

## 5. Fillet & Chamfer Variants

| Feature                 | Selection             | Purpose                                  | COM API / Type                    | Status |
|-------------------------|----------------------|------------------------------------------|-----------------------------------|--------|
| Constant Radius Fillet | Edges                 | Uniform radius rounding                  | `FeatureFillet` Type=Simple       | ✅      |
| Variable Radius Fillet | Edges + per-vertex R  | Radius changes along edge                | `FeatureFillet` Type=Multiple     | ❌      |
| Face Fillet            | Two faces             | Round between non-adjacent faces         | `FeatureFillet` Type=FaceFillet   | ❌      |
| Full Round Fillet      | Three face sets       | Replace face with full round             | `FeatureFillet` Type=FullRound    | ❌      |
| Distance-Distance Cham. | Edges + 2 distances   | Asymmetric chamfer                       | `InsertFeatureChamfer` Type=DistDist| ❌      |
| Angle-Distance Cham.   | Edges + dist + angle  | Slanted chamfer                          | `InsertFeatureChamfer` Type=AngleDist| ✅      |
| Vertex Chamfer         | Vertex + 3 distances  | Chamfer at corner                        | `InsertFeatureChamfer` Type=Vertex| ❌      |

---

## 6. Shell / Draft / Rib / Wrap

| Feature       | Input                        | Purpose                              | COM API                       | Status |
|---------------|------------------------------|--------------------------------------|-------------------------------|--------|
| Shell        | Body + face(s) to remove     | Uniform hollow                       | `InsertFeatureShell`         | ✅      |
| Multi-thickness Shell | Body + per-face thickness | Variable wall                        | `InsertFeatureShell` w/ list  | ❌      |
| Draft        | Faces + neutral plane + angle| Mold release taper                   | `InsertMultiFaceDraft`        | ✅      |
| Rib          | Open profile + thickness     | Stiffening web                       | `InsertRib`                   | ✅      |
| Wrap         | Sketch + cylindrical face    | Project/emboss text or curve         | `InsertWrap`                  | ❌      |
| Deform       | Body + control points        | Free-form shape change               | `InsertDeform`                | ❌      |

---

## 7. Reference Geometry (datums — required by many features)

| Feature           | Input                          | Purpose                              | COM API                       | Status |
|-------------------|--------------------------------|--------------------------------------|-------------------------------|--------|
| Reference Plane  | Face/plane + offset/angle      | New construction plane               | `InsertRefPlane`              | ❌ ⚠️   |
| Reference Axis   | Edge / two planes / cylinder   | Construction axis                    | `InsertAxis2`                 | ❌ ⚠️   |
| Reference Point  | Vertex / center                | Construction point                   | `InsertRefPoint`              | ❌      |
| Coordinate System| Origin + axes                  | Local frame for export/measure       | `InsertRefCoordSys`           | ❌      |
| Sketch on Plane  | New plane reference            | Construction sketch                  | (same as sketch op)           | ⚠️      |

**⚠️ Priority 1**: Reference plane and axis are blockers for many downstream
features (circular pattern about an arbitrary axis, sweep paths off a face,
lofted sections at offsets). Implement these next.

---

## 8. Combine / Boolean / Body Operations

| Feature     | Input               | Purpose                            | COM API                       | Status |
|-------------|--------------------|------------------------------------|-------------------------------|--------|
| Combine    | 2+ bodies          | Add / Subtract / Common            | `InsertCombineFeature`        | ❌      |
| Split      | Body + cutting tool| Divide body into pieces            | `InsertSplitBodyFeature`      | ❌      |
| Intersect  | Bodies + region    | Keep only intersection             | `InsertIntersectFeature`      | ❌      |
| Move/Copy  | Body + transform   | Reposition body in space           | `MoveCopyBody3`               | ❌      |
| Delete Body| Body               | Remove body from part              | `InsertDeleteBody`            | ❌      |
| Save Bodies| Bodies + paths     | Export bodies as new parts         | `SaveBodies`                  | ❌      |

---

## 9. Surface Features (zero-thickness)

| Feature           | Sketch / Input             | Purpose                          | COM API                            | Status |
|-------------------|----------------------------|----------------------------------|-------------------------------------|--------|
| Extrude Surface  | Open or closed             | Linear surface                   | `InsertExtrudeRefSurface`           | ❌      |
| Revolve Surface  | Profile + centerline       | Rotational surface               | `InsertRevolveRefSurface`           | ❌      |
| Sweep Surface    | Profile + path             | Swept surface                    | `InsertSweepRefSurface`             | ❌      |
| Loft Surface     | 2+ profiles                | Blended surface                  | `InsertLoftRefSurface`              | ❌      |
| Boundary Surface | Boundary curve sets        | Surface from 4-edge patch        | `InsertBoundaryRefSurface`          | ❌      |
| Fill Surface     | Closed boundary            | Patch a hole                     | `InsertFillSurface`                 | ❌      |
| Knit Surface     | Multiple surfaces          | Join surfaces                    | `InsertKnitSurface`                 | ❌      |
| Trim Surface     | Surface + trimming tool    | Cut surface to bounds            | `InsertTrimSurface2`                | ❌      |
| Extend Surface   | Surface + edge + distance  | Stretch surface                  | `InsertExtendSurface`               | ❌      |
| Planar Surface   | Closed sketch              | Flat surface                     | `InsertPlanarSurfaceFromSketch`     | ❌      |

---

## 10. Sketching primitives (sketch entities)

These are the building blocks our sketch ops emit. Each maps to a SketchManager
method.

| Primitive       | Closed?     | Defines what                          | COM API                                  | Status |
|----------------|-------------|---------------------------------------|------------------------------------------|--------|
| Line           | Open        | Straight segment                      | `CreateLine`                             | ✅      |
| Corner Rect    | Closed      | Axis-aligned rectangle                | `CreateCornerRectangle`                   | ✅      |
| Center Rect    | Closed      | Centered rectangle                    | `CreateCenterRectangle`                   | ✅      |
| Circle Radius  | Closed      | Circle by radius                      | `CreateCircleByRadius`                    | ✅      |
| Circle Center  | Closed      | Circle by 2 points                    | `CreateCircle`                            | ⚠️      |
| Arc Center     | Open        | Arc by center + endpoints             | `CreateArc`                              | ❌      |
| Arc Tangent    | Open        | Arc tangent to last segment          | `CreateTangentArc`                        | ❌      |
| Ellipse        | Closed      | Major/minor axis ellipse              | `CreateEllipse2`                          | ❌      |
| Spline         | Open/closed | Free-form curve                       | `CreateSpline2`                           | ❌      |
| Polygon        | Closed      | N-sided regular polygon               | `CreatePolygon`                           | ❌      |
| Slot (straight)| Closed      | Rounded-end slot                      | `CreateStraightSlot`                      | ❌      |
| Slot (arc)     | Closed      | Curved slot                           | `CreateArcSlot`                           | ❌      |
| Text           | Closed      | Sketch text outline                   | `CreateText` + `InsertSketchText`         | ❌      |
| Construction   | n/a         | Marks any entity as construction      | `SetConstructionState`                    | ⚠️      |

**Centerline** = a construction `Line` with construction toggle ON, required by
revolve, used as the axis of rotation.

---

## 11. Sketch Relations & Dimensions

Every fully-defined sketch needs relations + dimensions. These are the
constraint types our executor must know how to apply.

### Relations
| Relation        | Applies to         | Effect                                         |
|-----------------|--------------------|------------------------------------------------|
| Coincident     | 2 points / pt+ln   | Forces overlap                                  |
| Concentric    | 2 arcs/circles     | Shared center                                   |
| Tangent       | Curve + line/curve | Tangent contact                                 |
| Parallel      | 2 lines            | Same direction                                  |
| Perpendicular | 2 lines            | 90° between                                     |
| Horizontal    | Line/point pair    | Aligned to X                                    |
| Vertical      | Line/point pair    | Aligned to Y                                    |
| Equal         | 2 entities         | Same length / radius                            |
| Symmetric     | Entities + line    | Reflected across centerline                     |
| Fix           | Anything           | Pin in place (Codex's sgFIXED fallback uses this)|
| Midpoint      | Point + segment    | Point at segment midpoint                       |
| Coradial      | 2 arcs             | Concentric AND equal radius                     |

### Dimensions
| Dimension type | API                              | Use                            |
|----------------|----------------------------------|--------------------------------|
| Linear         | `AddDimension2`                  | Distance, length               |
| Horizontal     | `AddHorizontalDimension2`        | X-direction distance           |
| Vertical       | `AddVerticalDimension2`          | Y-direction distance           |
| Radial         | `AddRadialDimension2`            | Arc/circle radius              |
| Diameter       | `IAddDiameterDimension2`         | Circle diameter                |
| Angular        | `AddAngularDimension2`           | Angle between lines            |
| Distance       | `AddDistanceDimension2`          | Generic point-to-point         |

Setting `swInputDimValOnCreate = false` at addin init prevents the Modify
dialog from popping up for every dimension created programmatically.

---

## 12. Implementation Priority (next batch)

Based on engineering impact × user-facing breadth, here's the order to fill the
remaining gaps:

### Priority 1 (unlocks downstream features)
1. **Reference Plane** — required for sketches on offsets, lofts at heights,
   patterns about custom axes. Many other features depend on this.
2. **Reference Axis** — required for circular patterns about non-temporary axes,
   revolve about custom directions.
3. **Lofted Boss / Cut** — first non-trivial multi-section feature; gateway to
   ergonomic shapes.

### Priority 2 (common engineering ops)
4. **Swept Cut** — slots along curves, fluid channels.
5. **Variable Radius Fillet** — industrial design rounding.
6. **Combine (Add/Subtract/Common)** — body-level boolean ops.
7. **Thread** — threaded shafts, tapped holes that aren't simulated.

### Priority 3 (specialised)
8. **Wrap** — emboss text on cylindrical bodies.
9. **Series of Holes** — bolt rows on plates.
10. **Sketch-Driven Pattern** — patterns at arbitrary points from a control
    sketch.

### Priority 4 (surface modelling)
11. Extrude / Revolve / Loft Surface — needed for sheet metal precursors and
    advanced curve modelling.
12. Boundary Surface, Fill Surface, Knit Surface.

---

## 13. How the planner uses this catalog

1. **Intent classification**: when the user prompt arrives, the LLM (or pattern
   router) classifies which feature category is being requested.
2. **Sketch synthesis**: the catalog tells the planner what sketch type the
   target feature needs. The planner emits the sketch op first.
3. **Feature emission**: the planner emits the consuming feature op, referencing
   the sketch by `id`.
4. **Validation**: the validator checks that the sketch type matches the
   feature requirement (e.g., revolve must have a centerline + closed profile).
5. **Repair**: if the executor returns an error, the lessons-learned memory
   (see `learn/failure_memory.py`) injects past failure patterns to prevent
   the LLM from emitting the same broken plan twice.

This catalog is the planner's mental model of SolidWorks. When you add a new
feature, add it here first, ingest it into RAG, then implement the schema +
executor handler.
