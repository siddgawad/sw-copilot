# Validation Harness Design — build123d Headless Backend

**Status:** Phase 1 (foundation) in progress
**Owner:** Claude (foundation) + Codex/Haiku/Sonnet (handlers)
**Goal:** Run any `OperationGraph` headlessly in build123d, compare result to SolidWorks output, fail fast in CI before a graph ever hits SW.

---

## Why

Today, the only way to test a generated operation graph is to open SolidWorks and watch it run. This is slow, requires Windows, blocks CI, and means every regression is caught at runtime. build123d (Apache-2.0, OCCT kernel) supports the same primitives we need (sketch, extrude, hole, fillet, chamfer, pattern). If we run the graph there first:

1. CI runs every PR on Ubuntu in 30 seconds (no SolidWorks license needed)
2. Bad coordinates / impossible geometry caught before COM
3. Regressions caught the moment they're introduced, not on demo day
4. Validation tolerance becomes a number, not "did SW crash"

---

## Non-Goals (don't expand scope)

- Replacing SolidWorks. build123d is a **validator**, not a target.
- Drawings, title blocks, export — SW-only operations are explicitly skipped.
- Visual rendering. We compare topology (bbox, body count, feature count, sketch entity count), not pixels.

---

## Architecture

```
   OperationGraph (Pydantic, from /generate)
         │
         ▼
   Build123dBackend.execute(graph) ──▶ Build123dResult
         │                              ├─ success: bool
         │                              ├─ bounding_box_mm: BoundingBox
   ┌─────┴──────┐                       ├─ body_count: int
   │  OpHandler │                       ├─ feature_count: int
   │  Registry  │                       ├─ sketches: list[...]
   └─────┬──────┘                       └─ errors: list[str]
         │
         ├── create_part_handler
         ├── create_sketch_handler
         ├── extrude_boss_handler
         ├── hole_wizard_handler           ◀── DELEGATABLE
         ├── fillet_handler                ◀── DELEGATABLE
         └── ... (one file per op type)
```

**Key contract:** `Build123dResult` mirrors `models.schemas.PartReport` shape so the **existing** `validation_agent.validate()` works against build123d output with zero changes. No new validator code paths.

---

## File Layout

```
agent-backend/
├── validation/
│   ├── __init__.py                  # public: Build123dBackend, Build123dResult
│   ├── backend.py                   # Build123dBackend class
│   ├── context.py                   # ExecutionContext (mutable per-graph state)
│   ├── result.py                    # Build123dResult dataclass + bbox match helper
│   ├── plane_mapper.py              # str → build123d.Plane lookup
│   └── op_handlers/
│       ├── __init__.py              # HANDLERS registry dict
│       ├── base.py                  # OpHandler ABC
│       ├── primitives.py            # create_part / sketch / rectangle / circle / extrude  (CLAUDE)
│       ├── hole_wizard.py           # hole_wizard handler                                  (DELEGATABLE)
│       ├── edge_finish.py           # fillet + chamfer                                     (DELEGATABLE)
│       ├── pattern.py               # circular_pattern + linear_pattern + mirror           (DELEGATABLE)
│       └── meta.py                  # rebuild + noop + delete_feature (validation-only)    (CLAUDE)
└── tests/validation/
    ├── conftest.py                  # shared graph fixtures
    ├── test_backend_smoke.py        # end-to-end: empty graph → empty result
    ├── test_primitives.py           # one box, one cylinder, one plate
    ├── test_hole_wizard.py          # DELEGATABLE — one test per hole_type
    ├── test_edge_finish.py          # DELEGATABLE
    ├── test_pattern.py              # DELEGATABLE
    └── test_pattern_parity.py       # every deterministic pattern.try_generate ↔ build123d
.github/workflows/validation.yml     # headless CI
```

---

## Core Interfaces (immutable — don't change without coordination)

### `OpHandler` (in `op_handlers/base.py`)

```python
class OpHandler(ABC):
    op_type: str  # e.g. "extrude_boss"

    @abstractmethod
    def execute(self, op: OperationDto, ctx: ExecutionContext) -> None:
        """Mutate ctx in place. Raise on geometric error.
        Never swallow exceptions — the registry catches and records them."""
```

### `ExecutionContext` (in `context.py`)

```python
@dataclass
class ExecutionContext:
    parts: dict[str, Part] = field(default_factory=dict)        # op_id → built Part
    sketches: dict[str, Sketch] = field(default_factory=dict)   # sketch_id → Sketch
    features: dict[str, str] = field(default_factory=dict)      # op_id → "boss"|"cut"|"hole"|...
    active_part_id: str | None = None
    active_sketch_id: str | None = None
    errors: list[str] = field(default_factory=list)

    def add_error(self, op_id: str, msg: str) -> None: ...
    def to_result(self) -> Build123dResult: ...
```

### `Build123dResult` (in `result.py`)

```python
@dataclass(frozen=True)
class Build123dResult:
    success: bool
    bounding_box_mm: BoundingBox | None
    body_count: int
    feature_count: int
    sketches: list[SketchInfo]
    errors: list[str]

    def matches_part_report(self, report: PartReport, tolerance_mm: float = 0.5) -> bool: ...
```

### `Build123dBackend` (in `backend.py`)

```python
class Build123dBackend:
    def __init__(self) -> None: ...                # build registry
    def execute(self, graph: OperationGraph) -> Build123dResult: ...
```

That's the entire public surface. Handlers are private.

---

## Delegation Pattern — How a Handler Gets Built

Every handler file follows this exact template so any model can implement one without reading the rest of the codebase:

```python
"""hole_wizard handler — counterbore / clearance / countersink / tapped.

Maps OperationDto fields to build123d primitives. Pure Python, no COM.
Inputs validated by Pydantic on OperationDto; only geometric checks here.
"""
from build123d import BuildPart, Hole, CounterBoreHole, CounterSinkHole, Locations, Plane
from models.schemas import OperationDto
from standards.dimension_resolver import resolve_clearance_hole, resolve_counterbore
from ..base import OpHandler
from ..context import ExecutionContext


class HoleWizardHandler(OpHandler):
    op_type = "hole_wizard"

    def execute(self, op: OperationDto, ctx: ExecutionContext) -> None:
        # 1. Resolve active part — raise if none.
        part = self._active_part(ctx)
        # 2. Resolve fastener dimensions from ISO standards.
        dims = self._resolve_dimensions(op)
        # 3. Compute Locations from op.positions (xy plane of top face).
        locations = self._positions_to_locations(op.positions)
        # 4. Build the hole feature in the BuildPart context.
        self._cut(part, op.hole_type, dims, locations, op.through_all, op.depth_mm)
        # 5. Register the result feature id in ctx.features.
        ctx.features[op.id] = "hole"

    # ── helpers — each one fully specced below ────────────────────────
    def _active_part(self, ctx: ExecutionContext) -> Part: ...
    def _resolve_dimensions(self, op: OperationDto) -> HoleDims: ...
    def _positions_to_locations(self, positions: list[HolePositionDto]) -> Locations: ...
    def _cut(self, part: Part, hole_type: str, dims: HoleDims,
             locs: Locations, through_all: bool, depth_mm: float) -> None: ...
```

Each `...` is a separate, independent function with:
- explicit signature
- one-paragraph docstring
- pre-conditions / post-conditions in plain English
- 1 happy-path test + 1 failure test in the matching `test_*.py`

A Haiku-level model can implement one function per turn without needing to understand the rest.

---

## Phasing & Split

### Phase 1 — Foundation (Claude, ~3 hours)
- [ ] `requirements.txt` — pin `build123d>=0.7.0`
- [ ] Scaffold all 7 files in `validation/` with full type signatures + docstrings
- [ ] Implement `Build123dBackend`, `ExecutionContext`, `Build123dResult`, `PlaneMapper`, `OpHandler`, `HANDLERS` registry
- [ ] Implement `primitives.py` (create_part, create_sketch, rectangle, circle, extrude_boss, extrude_cut)
- [ ] Implement `meta.py` (rebuild, noop, delete_feature-as-validation)
- [ ] `tests/validation/test_backend_smoke.py` + `test_primitives.py` passing
- [ ] `.github/workflows/validation.yml` green on a tiny graph

### Phase 2 — Delegated handlers (Haiku/Sonnet/Codex, ~1 day total)
Each is a self-contained file + matching test file. Pick up in any order:
- [ ] `hole_wizard.py` + `test_hole_wizard.py`
- [ ] `edge_finish.py` (fillet + chamfer) + `test_edge_finish.py`
- [ ] `pattern.py` (circular + linear + mirror) + `test_pattern.py`

### Phase 3 — Parity (Claude, ~2 hours)
- [ ] `test_pattern_parity.py` — run every `patterns/*.py.try_generate` through build123d, assert declared bbox matches build123d bbox within 0.5 mm
- [ ] Add `Build123dValidationError` to surface to `/generate` (optional new `/validate-plan` endpoint)

### Phase 4 — Wire into the pipeline (later, post-stable)
- [ ] Add optional `validate_with_build123d: bool` flag to `/generate` response
- [ ] Surface validation diff in C# task pane

---

## Risks & Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| build123d wheel install fails on Windows venv | Medium | Test in `requirements-dev.txt` first; fall back to `pip install --only-binary :all:` if needed. CI runs on Ubuntu where wheels are clean. |
| OCCT bbox differs from SolidWorks by >0.5mm on some ops | Medium | Tolerance is a knob (`tolerance_mm`). Default 0.5 for plates/boxes; relax to 1.0 for fillet/chamfer. |
| Counterbore semantics differ between build123d and SW | Low | Codex implements both pocket + clearance cut explicitly; tests verify the depth and diameter independently. |
| Pattern handler creates duplicates at origin | Medium | Test asserts `body_count` stays at 1 for boolean-merged patterns. |
| CI runtime balloons as handlers grow | Low | Each handler test is a single graph with ≤5 ops. Whole suite caps at 30 seconds. |

---

## Acceptance Criteria

Phase 1 is **done** when:
- `pytest agent-backend/tests/validation/ -q` is green
- `Build123dBackend().execute(plate.try_generate("create a 100x60x5mm plate"))` returns `BoundingBox(100, 60, 5)` ±0.5mm
- CI workflow runs on a fresh PR and passes

Phase 2 is **done** when:
- All 12 op types in active use have a handler
- Each handler file has ≥2 tests (happy + failure)
- Parity test runs every deterministic pattern through build123d without errors

Phase 3 is **done** when:
- Every committed `OperationGraph` from `patterns/` produces a `Build123dResult` with `success=True` and bbox matching the spec
- A divergence between Python intent and build123d execution fails CI

---

## How to Pick Up Work

1. Read this doc
2. Check `TaskList` — claim a `DELEGATABLE` task by setting yourself as owner
3. Open the matching scaffolded file in `agent-backend/validation/op_handlers/`
4. Implement one function at a time, run its test, commit
5. Mark task completed, pick the next

Each handler file is independent. Two agents can work on two handlers in parallel without touching the same file.
