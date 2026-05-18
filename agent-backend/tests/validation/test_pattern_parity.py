"""Pattern-parity tests: every deterministic pattern.try_generate result
must execute cleanly in build123d and produce a bbox matching its declared
dimensions.

This is the test that catches the "Top Plane swapped my Y and Z" class of
regression at PR time, not at demo time.

The cases cover demo-critical deterministic patterns that should be
validated in CI before they ever reach SolidWorks.
"""
from __future__ import annotations

import pytest

from patterns import bracket, enclosure, flange, plate
from patterns.shaft import try_generate_shaft
from validation import Build123dBackend


PARITY_CASES = [
    # (prompt, expected_bbox_mm, generator)
    ("create a 100x60x5mm plate", (100.0, 60.0, 5.0), plate.try_generate),
    ("plate 200mm x 150mm x 6mm", (200.0, 150.0, 6.0), plate.try_generate),
    ("create a plate 100x100x5mm", (100.0, 100.0, 5.0), plate.try_generate),
    ("base plate 300x200x10mm", (300.0, 200.0, 10.0), plate.try_generate),
    (
        "flange 100mm OD 6mm thick with 6 M8 holes on 80mm PCD",
        (100.0, 100.0, 6.0),
        flange.try_generate,
    ),
    ("create an L-bracket 80x60x5mm", (80.0, 65.0, 60.0), bracket.try_generate),
    (
        "create an enclosure 120x80x50mm with 3mm walls",
        (120.0, 80.0, 50.0),
        enclosure.try_generate,
    ),
    (
        "40mm shaft 100mm long with 80mm flange 10mm thick",
        (80.0, 80.0, 110.0),
        try_generate_shaft,
    ),
]


@pytest.mark.parametrize("prompt,expected_bbox,generator", PARITY_CASES)
def test_primitive_pattern_bbox_parity(prompt, expected_bbox, generator):
    """Every critical pattern must produce a bbox within 0.5mm of expected."""
    graph = generator(prompt)
    assert graph is not None, f"Pattern did not match: {prompt!r}"

    result = Build123dBackend().execute(graph)
    assert result.success, f"build123d failed on {prompt!r}: {result.errors}"
    bb = result.bounding_box_mm
    assert bb is not None
    ex, ey, ez = expected_bbox
    assert bb.x_mm == pytest.approx(ex, abs=0.5), f"x mismatch for {prompt!r}"
    assert bb.y_mm == pytest.approx(ey, abs=0.5), f"y mismatch for {prompt!r}"
    assert bb.z_mm == pytest.approx(ez, abs=0.5), f"z mismatch for {prompt!r}"
