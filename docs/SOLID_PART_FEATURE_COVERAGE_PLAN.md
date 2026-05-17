# Solid Part Feature Coverage Plan

Date: 2026-05-16

Goal: make SW Copilot reliably create and edit SolidWorks part models with
fully defined sketches and deterministic, machineable feature operations.

This is the working route for Claude + Codex. Do not jump to arbitrary
free-form modeling before the lower layers are proven.

## Layer 0: Sketch Definition Contract

Status: started, compile/test verified. Live UI verification still required.

Required for every profile-producing operation:

- geometry entities are created at deterministic coordinates
- driving Smart Dimensions are added for size
- position is locked to origin, datum, or parent face reference
- sketch relations are applied where appropriate
- `FullyDefineSketch` is used only as a cleanup pass, not as the only source of
  design intent
- `ExtractPartReport()` reports sketch entity count and dimension count
- live SolidWorks test confirms sketch is black / fully defined

Current Codex patch:

- rectangles: horizontal + vertical dimensions, origin relation attempt,
  `FullyDefineSketch`
- circles: diameter dimensions, center dimensions/relations,
  `FullyDefineSketch`
- generic sketches: `FullyDefineSketch` before close
- hole fallback sketches: diameter + center dimensions/relations before cut
- deterministic box/cylinder/follow-up feature graphs now carry `_v0`
  `part_family` markers so failures do not enter LLM repair loops

Open:

- expose sketch definition status if the API provides a reliable value
- add validation warnings/errors for missing sketch dimensions after live
  report format is confirmed
- tune circle-array auto-definition if SolidWorks over-defines holes

## Layer 1: Existing Feature Families To Stabilize

These exist and should be made production-grade before adding more features:

| Feature | Current op | Owner | Next gate |
|---|---|---|---|
| Extrude boss | `extrude_boss` | Codex | live test boxes/cylinders/plates |
| Extrude cut | `extrude_cut` | Codex | through-all and blind cuts on top face |
| Simple holes | `hole_wizard` fallback | Codex | live test M3-M12 positions, through-all |
| Counterbores | `hole_wizard` counterbore | Codex | live test clearance through-hole + blind pocket direction |
| Fillet | `fillet` | Codex | external-edge selection, avoid internal hole edges |
| Chamfer | `chamfer` | Codex | top-edge selector and external-edge selection |
| Revolve | `revolve` | Codex + Claude | deterministic centerline sketches |
| Linear pattern | `linear_pattern` | Codex | selected-feature pattern live test |
| Circular pattern | `circular_pattern` | Codex | axis selection live test |
| Mirror | `mirror` | Codex | mirror plane + feature selection live test |

## Layer 2: Missing Common Solid Part Features

Add these as explicit OperationGraph ops only after Layer 1 passes:

| Feature | Proposed op | Notes |
|---|---|---|
| Shell | `shell` | needs face selection and wall thickness |
| Draft | `draft` | needs neutral plane/face and angle |
| Sweep boss/cut | `sweep_boss`, `sweep_cut` | needs profile sketch + path sketch |
| Loft boss/cut | `loft_boss`, `loft_cut` | needs multiple profile sketches |
| Rib | `rib` | needs open sketch, thickness, direction |
| Reference plane | `create_reference_plane` | needed for multi-plane features |
| Axis | `create_axis` | needed for revolve/pattern reliability |
| Equation/global variable | `set_equation` | drive parametric dimensions |
| Configuration | `create_configuration` | future product variants |
| Material | `set_material` | mass and manufacturing context |

Each new op must include:

- Python Pydantic schema
- C# DTO fields
- executor handler
- planner prompt examples
- backend schema tests
- C# build gate
- live SolidWorks smoke test
- one negative test/refusal rule

## Layer 3: Manufacturability Intelligence

Claude owns research/planning, Codex owns executor:

- GD&T-aware drawing checks
- ISO/ASME fastener and clearance dimensions from deterministic tables
- minimum wall, boss, rib, draft, fillet/chamfer rules
- machining process hints: milled, turned, sheet metal, printed
- no exact standards values from LLM memory

## Immediate Next Tasks

1. Live-test the exact sequence in
   `docs/CODEX_LIVE_FAILURE_FIX_PLAN_2026-05-16.md`.
2. Fix any counterbore blind-cut direction, over-definition, or top-edge
   selection failures found in SolidWorks.
3. Make validation consume `dimension_count` once live reports are confirmed.
4. Harden fillet/chamfer to select external body edges first for all-edge
   requests, not just top-edge requests.
5. Add `shell` and `draft` as the first missing solid-feature ops.

## Acceptance Bar

A supported prompt is not done until:

- the graph validates
- the C# executor succeeds
- the part rebuilds
- sketches are fully defined or explicitly documented as intentionally flexible
- a PartReport proves body/features/sketches/dimensions exist
- live SolidWorks behavior matches the report
