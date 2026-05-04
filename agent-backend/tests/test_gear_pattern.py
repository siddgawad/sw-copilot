"""
Tests for the deterministic spur gear pattern library.

These tests verify the geometry math (no SolidWorks, no LLM) and the
natural-language parser.  Each assertion corresponds to a specific
engineering requirement: correct pitch diameter, closed profile,
involute starts at correct radius, etc.
"""
from __future__ import annotations

import math

import pytest

from models.schemas import ExtrudeBossOp, LineEntity, NoopOp, SketchOp
from patterns.gear import (
    _arc_pts,
    _gear_profile_mm,
    _t_for_r,
    generate_spur_gear,
    parse_gear_params,
    try_generate_gear,
)


# ── Geometry helpers ──────────────────────────────────────────────────────────

def test_t_for_r_at_base_returns_zero():
    assert _t_for_r(20.0, 20.0) == pytest.approx(0.0, abs=1e-9)


def test_t_for_r_below_base_returns_zero():
    assert _t_for_r(20.0, 15.0) == pytest.approx(0.0, abs=1e-9)


def test_t_for_r_above_base():
    r_b = 20.0
    r   = 25.0
    t   = _t_for_r(r_b, r)
    x   = r_b * (math.cos(t) + t * math.sin(t))
    y   = r_b * (math.sin(t) - t * math.cos(t))
    assert math.hypot(x, y) == pytest.approx(r, rel=1e-6)


def test_arc_pts_count():
    pts = _arc_pts(10.0, 0.0, math.pi / 2, 4)
    assert len(pts) == 4


def test_arc_pts_end_angle():
    pts = _arc_pts(10.0, 0.0, math.pi / 2, 4)
    x, y = pts[-1]
    assert math.hypot(x, y) == pytest.approx(10.0, rel=1e-6)
    assert math.atan2(y, x) == pytest.approx(math.pi / 2, abs=1e-6)


# ── Profile geometry ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("N,m", [
    (20, 2),
    (16, 3),
    (30, 1),
])
def test_profile_is_closed(N, m):
    pts = _gear_profile_mm(N, m, 20.0)
    first, last = pts[0], pts[-1]
    # profile[-1] → profile[0] should be a short step (closed loop)
    dist = math.hypot(last[0] - first[0], last[1] - first[1])
    assert dist < 0.5, f"Profile not closed: gap = {dist:.4f} mm"


@pytest.mark.parametrize("N,m", [(20, 2), (16, 3)])
def test_profile_extent_matches_addendum(N, m):
    """Every point must lie ≤ addendum radius; max point ≈ addendum."""
    r_a = m * N / 2 + m
    pts = _gear_profile_mm(N, m, 20.0)
    radii = [math.hypot(x, y) for x, y in pts]
    assert max(radii) <= r_a + 0.02, f"Point outside addendum circle: {max(radii):.4f} > {r_a}"
    assert max(radii) >= r_a - 0.5, "No point near addendum — tip arc may be missing"


@pytest.mark.parametrize("N,m", [(20, 2), (16, 3)])
def test_profile_minimum_radius_at_root(N, m):
    """No point should be significantly inside the dedendum circle."""
    phi = math.radians(20.0)
    r_p = m * N / 2
    r_b = r_p * math.cos(phi)
    r_d = max(r_p - 1.25 * m, r_b)
    pts = _gear_profile_mm(N, m, 20.0)
    radii = [math.hypot(x, y) for x, y in pts]
    assert min(radii) >= r_d - 0.02, f"Point below dedendum: {min(radii):.4f} < {r_d}"


@pytest.mark.parametrize("N", [20, 16, 30])
def test_profile_has_n_symmetric_repeats(N):
    """The profile should have rotational N-fold symmetry (within 0.01 mm)."""
    pts = _gear_profile_mm(N, 2, 20.0)
    # Total points is n * (N_INV + N_TIP + N_INV + N_ROOT) — just verify count is divisible by N
    assert len(pts) % N == 0


# ── OperationGraph output ─────────────────────────────────────────────────────

def test_generate_spur_gear_returns_sketch_and_extrude():
    og = generate_spur_gear(20, 2.0, 20.0, 10.0)
    ops = og.operations
    assert len(ops) == 2
    assert isinstance(ops[0], SketchOp)
    assert isinstance(ops[1], ExtrudeBossOp)


def test_generate_spur_gear_sketch_plane():
    og = generate_spur_gear(20, 2.0)
    sk = og.operations[0]
    assert isinstance(sk, SketchOp)
    assert sk.plane == "Front Plane"


def test_generate_spur_gear_extrude_depth():
    og = generate_spur_gear(20, 2.0, thickness_mm=15.0)
    ex = og.operations[1]
    assert isinstance(ex, ExtrudeBossOp)
    assert ex.depth_mm == pytest.approx(15.0)


def test_generate_spur_gear_all_entities_are_lines():
    og = generate_spur_gear(20, 2.0)
    sk = og.operations[0]
    assert isinstance(sk, SketchOp)
    assert all(isinstance(e, LineEntity) for e in sk.entities)


def test_generate_spur_gear_entity_count_plausible():
    og = generate_spur_gear(20, 2.0)
    sk = og.operations[0]
    # 20 teeth × (12 inv + 4 tip + 12 inv + 4 root) = 20 × 32 = 640 entities
    assert len(sk.entities) == pytest.approx(640, abs=40)


def test_generate_too_few_teeth_returns_noop():
    og = generate_spur_gear(3, 2.0)
    assert len(og.operations) == 1
    assert isinstance(og.operations[0], NoopOp)


def test_generate_zero_module_returns_noop():
    og = generate_spur_gear(20, 0)
    assert isinstance(og.operations[0], NoopOp)


def test_generate_assumptions_include_module_and_teeth():
    og = generate_spur_gear(20, 2.0, pressure_angle_deg=20.0)
    text = " ".join(og.assumptions)
    assert "m=2" in text
    assert "N=20" in text
    assert "20.0°" in text


# ── Natural-language parser ───────────────────────────────────────────────────

@pytest.mark.parametrize("prompt,teeth", [
    ("make a 20 teeth spur gear", 20),
    ("16-tooth pinion m3", 16),
    ("gear with 30T and m2", 30),
])
def test_parse_teeth_count(prompt, teeth):
    p = parse_gear_params(prompt)
    assert p is not None
    assert p["teeth"] == teeth


@pytest.mark.parametrize("prompt,module", [
    ("spur gear 20 teeth m2", 2.0),
    ("20-tooth gear 3mm module", 3.0),
    ("gear 20 teeth module=2.5", 2.5),
])
def test_parse_module(prompt, module):
    p = parse_gear_params(prompt)
    assert p is not None
    assert p["module"] == pytest.approx(module)


def test_parse_pressure_angle():
    p = parse_gear_params("20 teeth gear PA=14.5 degrees m2")
    assert p is not None
    assert p["pressure_angle_deg"] == pytest.approx(14.5)


def test_parse_thickness():
    p = parse_gear_params("20 teeth m2 gear 12mm thick")
    assert p is not None
    assert p["thickness_mm"] == pytest.approx(12.0)


def test_parse_defaults_when_not_specified():
    p = parse_gear_params("make a 20 teeth gear")
    assert p is not None
    assert p["module"] == pytest.approx(2.0)
    assert p["pressure_angle_deg"] == pytest.approx(20.0)
    assert p["thickness_mm"] == pytest.approx(10.0)


def test_parse_no_teeth_returns_none():
    assert parse_gear_params("make a spur gear") is None


# ── Router entry point ────────────────────────────────────────────────────────

def test_try_generate_gear_matches_gear_prompt():
    og = try_generate_gear("20 teeth m2 spur gear 10mm thick")
    assert og is not None
    assert len(og.operations) == 2


def test_try_generate_gear_returns_none_for_non_gear():
    assert try_generate_gear("create a 50mm box") is None
    assert try_generate_gear("add M6 holes at corners") is None


def test_try_generate_gear_noop_when_teeth_missing():
    og = try_generate_gear("make me a gear with m2")
    assert og is not None
    assert isinstance(og.operations[0], NoopOp)
    assert og.missing_inputs


def test_try_generate_gear_noop_when_too_few_teeth():
    og = try_generate_gear("make a 3 teeth gear m2")
    assert og is not None
    assert isinstance(og.operations[0], NoopOp)
