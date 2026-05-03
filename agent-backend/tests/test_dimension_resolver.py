# Regression tests for the deterministic standards lookup tables and the
# repair-mode detector. These are the load-bearing components that replace
# vector search for exact engineering numbers — silent corruption of a single
# entry would propagate to every generated part. Lock the values with explicit
# spot checks against the published ISO standards.

import pytest

from standards.dimension_resolver import (
    build_standards_context,
    extract_fasteners_from_prompt,
    resolve_clearance_hole,
    resolve_counterbore,
    resolve_edge_inset,
    resolve_hex_nut,
    resolve_tap_drill,
    resolve_washer,
    resolve_all,
)
from agents.macro_engineer import _has_execution_error
from models.schemas import ConversationMessage


# ── ISO 273 clearance holes ───────────────────────────────────────────────────

@pytest.mark.parametrize("size,fit,expected", [
    ("M3",  "close",  3.2),
    ("M3",  "normal", 3.4),
    ("M3",  "loose",  3.6),
    ("M6",  "normal", 6.6),
    ("M8",  "normal", 9.0),
    ("M10", "normal", 11.0),
    ("M12", "normal", 13.5),
    ("M16", "normal", 17.5),
    ("M20", "normal", 22.0),
])
def test_clearance_hole_iso_273(size, fit, expected):
    row = resolve_clearance_hole(size, fit)
    assert row is not None
    assert row["diameter_mm"] == expected
    assert row["standard"] == "ISO 273"


def test_clearance_hole_unknown_size_returns_none():
    assert resolve_clearance_hole("M99") is None


def test_clearance_hole_invalid_fit_falls_back_to_normal():
    row = resolve_clearance_hole("M6", fit="garbage")
    assert row["diameter_mm"] == 6.6  # normal fit value


# ── ISO 4762 counterbores ─────────────────────────────────────────────────────

@pytest.mark.parametrize("size,cbore_dia,cbore_depth", [
    ("M3",  6.5,  3.0),
    ("M5",  9.5,  5.0),
    ("M6",  11.0, 6.0),
    ("M8",  14.0, 8.0),
    ("M10", 17.5, 10.0),
    ("M12", 20.0, 12.0),
])
def test_counterbore_iso_4762(size, cbore_dia, cbore_depth):
    row = resolve_counterbore(size)
    assert row is not None
    assert row["counterbore_diameter_mm"] == cbore_dia
    assert row["counterbore_depth_mm"] == cbore_depth


# ── ISO 4032 hex nuts ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("size,waf,height", [
    ("M3",  5.5,  2.4),
    ("M4",  7.0,  3.2),
    ("M5",  8.0,  4.7),
    ("M6",  10.0, 5.2),
    ("M8",  13.0, 6.8),
    ("M10", 17.0, 8.4),
    ("M12", 19.0, 10.8),
    ("M16", 24.0, 14.8),
    ("M20", 30.0, 18.0),
    ("M24", 36.0, 21.5),
])
def test_hex_nut_iso_4032(size, waf, height):
    row = resolve_hex_nut(size)
    assert row is not None
    assert row["width_across_flats_mm"] == waf
    assert row["nut_height_mm"] == height
    assert row["standard"] == "ISO 4032"


# ── ISO 7089 plain washers ────────────────────────────────────────────────────

@pytest.mark.parametrize("size,outer,thick", [
    ("M3",  7.0,  0.5),
    ("M5",  10.0, 1.0),
    ("M6",  12.0, 1.6),
    ("M8",  16.0, 1.6),
    ("M10", 20.0, 2.0),
    ("M12", 24.0, 2.5),
    ("M16", 30.0, 3.0),
    ("M20", 37.0, 3.0),
    ("M24", 44.0, 4.0),
])
def test_washer_iso_7089(size, outer, thick):
    row = resolve_washer(size)
    assert row is not None
    assert row["washer_outer_dia_mm"] == outer
    assert row["washer_thickness_mm"] == thick
    assert row["standard"] == "ISO 7089"


# ── Tap drill + thread engagement ─────────────────────────────────────────────

@pytest.mark.parametrize("size,drill,pitch", [
    ("M3",  2.5,  0.5),
    ("M6",  5.0,  1.0),
    ("M8",  6.8,  1.25),
    ("M10", 8.5,  1.5),
])
def test_tap_drill_iso_724(size, drill, pitch):
    row = resolve_tap_drill(size)
    assert row["drill_mm"] == drill
    assert row["pitch_mm"] == pitch


# ── Edge inset (design rule, not strict ISO) ──────────────────────────────────

def test_edge_inset_known_sizes():
    for size in ("M3", "M4", "M5", "M6", "M8", "M10", "M12", "M16", "M20"):
        row = resolve_edge_inset(size)
        assert row is not None
        assert row["inset_mm"] > 0


# ── Size normalisation ────────────────────────────────────────────────────────

@pytest.mark.parametrize("input,expected_diameter", [
    ("M6",  6.6),
    ("m6",  6.6),
    (" m6 ", 6.6),
    ("6",   6.6),
])
def test_normalisation(input, expected_diameter):
    row = resolve_clearance_hole(input)
    assert row is not None
    assert row["diameter_mm"] == expected_diameter


# ── Fastener extraction from free text ────────────────────────────────────────

def test_extract_fasteners_basic():
    sizes = extract_fasteners_from_prompt(
        "add four M6 counterbores and two M8 tapped holes"
    )
    assert sizes == ["M6", "M8"]


def test_extract_fasteners_dedupes():
    sizes = extract_fasteners_from_prompt("M6 M6 M6 m6")
    assert sizes == ["M6"]


def test_extract_fasteners_handles_decimal_sizes():
    sizes = extract_fasteners_from_prompt("use M2.5 screws")
    assert "M2.5" in sizes


def test_extract_fasteners_empty_when_no_fasteners():
    assert extract_fasteners_from_prompt("create a 50mm box") == []


# ── Combined resolve_all ──────────────────────────────────────────────────────

def test_resolve_all_m6_includes_all_categories():
    data = resolve_all("M6")
    assert data["clearance_hole_normal_mm"] == 6.6
    assert data["counterbore_diameter_mm"] == 11.0
    assert data["nut_width_across_flats_mm"] == 10.0
    assert data["washer_outer_dia_mm"] == 12.0
    assert data["tap_drill_mm"] == 5.0


# ── Standards context block injection ─────────────────────────────────────────

def test_build_standards_context_includes_nut_and_washer_lines():
    block, refs = build_standards_context("use M8 fasteners on this part")
    assert "M8 fastener" in block
    assert "Hex nut (ISO 4032)" in block
    assert "Plain washer (ISO 7089)" in block
    assert any("ISO 4032" in r for r in refs)
    assert any("ISO 7089" in r for r in refs)


def test_build_standards_context_no_fasteners_returns_empty():
    block, refs = build_standards_context("create a 100mm cube")
    assert block == ""
    assert refs == []


def test_build_standards_context_unknown_size_returns_empty():
    # Sizes that exist in the regex but not in any lookup table
    # should not produce a half-empty context block.
    block, refs = build_standards_context("use M99 fasteners")
    assert block == ""
    assert refs == []


# ── Repair-mode detector ──────────────────────────────────────────────────────

def test_repair_detector_none_history():
    assert _has_execution_error(None) is False


def test_repair_detector_empty_history():
    assert _has_execution_error([]) is False


def test_repair_detector_clean_run():
    history = [
        ConversationMessage(role="user", content="add holes"),
        ConversationMessage(role="assistant", content="Runtime: [h1] Hole Wizard on Top Plane"),
    ]
    assert _has_execution_error(history) is False


def test_repair_detector_finds_error_marker():
    history = [
        ConversationMessage(role="user", content="add holes"),
        ConversationMessage(role="assistant", content="Runtime: ERROR: Could not select top face"),
    ]
    assert _has_execution_error(history) is True


def test_repair_detector_finds_rule_violation_marker():
    history = [
        ConversationMessage(role="user", content="extrude that"),
        ConversationMessage(role="assistant", content="RULE VIOLATION: depth_mm must be positive"),
    ]
    assert _has_execution_error(history) is True


def test_repair_detector_only_inspects_most_recent_assistant_turn():
    # An old error followed by a clean turn should NOT trigger repair mode.
    history = [
        ConversationMessage(role="user", content="add holes"),
        ConversationMessage(role="assistant", content="Runtime: ERROR: bad face"),
        ConversationMessage(role="user", content="try again on Top Plane"),
        ConversationMessage(role="assistant", content="Runtime: [h1] Hole Wizard succeeded"),
    ]
    assert _has_execution_error(history) is False


def test_repair_detector_ignores_user_messages_containing_error_word():
    history = [
        ConversationMessage(role="user", content="ERROR: my last attempt failed, please fix"),
    ]
    # No assistant turn to inspect → not in repair mode.
    assert _has_execution_error(history) is False
