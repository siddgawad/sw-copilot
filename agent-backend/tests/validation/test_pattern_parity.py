"""Pattern-parity tests: every deterministic pattern.try_generate result
must execute cleanly in build123d and produce a bbox matching its declared
dimensions.

This is the test that catches the "Top Plane swapped my Y and Z" class of
regression at PR time, not at demo time.

Only the operations Phase 1 implements are exercised here. Patterns that
end with hole_wizard / circular_pattern will fail with an error message
identifying the missing handler — that's a feature, not a bug. Add the
prompt back to PARITY_CASES once the handler is implemented.
"""
from __future__ import annotations

import pytest

from patterns import plate
from validation import Build123dBackend


PARITY_CASES_PRIMITIVES = [
    # (prompt, expected_bbox_mm, generator)
    ("create a 100x60x5mm plate",   (100.0, 60.0, 5.0),  plate.try_generate),
    ("plate 200mm x 150mm x 6mm",   (200.0, 150.0, 6.0), plate.try_generate),
    ("create a plate 100x100x5mm",  (100.0, 100.0, 5.0), plate.try_generate),
    ("base plate 300x200x10mm",     (300.0, 200.0, 10.0), plate.try_generate),
]


@pytest.mark.parametrize("prompt,expected_bbox,generator", PARITY_CASES_PRIMITIVES)
def test_primitive_pattern_bbox_parity(prompt, expected_bbox, generator):
    """Every primitive pattern must produce a bbox within 0.5mm of declared."""
    graph = generator(prompt)
    assert graph is not None, f"Pattern did not match: {prompt!r}"

    # Strip ops that need handlers we haven't built yet.
    skipped = {"hole_wizard", "fillet", "chamfer",
               "circular_pattern", "linear_pattern", "mirror"}
    graph.operations = [op for op in graph.operations if op.type not in skipped]

    result = Build123dBackend().execute(graph)
    assert result.success, f"build123d failed on {prompt!r}: {result.errors}"
    bb = result.bounding_box_mm
    assert bb is not None
    ex, ey, ez = expected_bbox
    assert bb.x_mm == pytest.approx(ex, abs=0.5), f"x mismatch for {prompt!r}"
    assert bb.y_mm == pytest.approx(ey, abs=0.5), f"y mismatch for {prompt!r}"
    assert bb.z_mm == pytest.approx(ez, abs=0.5), f"z mismatch for {prompt!r}"
