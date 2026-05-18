"""Handler registry. Maps op.type strings → OpHandler instances.

Adding a new handler:
    1. Implement a subclass of OpHandler in its own .py file in this dir.
    2. Set its op_type class attribute (e.g. "fillet").
    3. Import and instantiate it below.
    4. Add it to the HANDLERS dict keyed by its op_type.

Don't merge two op types into one handler class — keeps tests focused and
makes parallel delegation safe.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .primitives import (
    CreatePartHandler,
    CreateSketchHandler,
    SketchHandler,
    AddCenterRectangleHandler,
    AddCirclesHandler,
    ExtrudeBossHandler,
    ExtrudeCutHandler,
)
from .meta import RebuildHandler, NoopHandler, DeleteFeatureHandler
from .hole_wizard import HoleWizardHandler
from .edge_finish import FilletHandler, ChamferHandler
from .pattern import CircularPatternHandler
from .solid_features import ShellHandler

if TYPE_CHECKING:
    from .base import OpHandler


def _build_registry() -> "dict[str, OpHandler]":
    """Instantiate one of each handler and key by op_type."""
    handlers = [
        # ── Phase 1: foundation primitives (CLAUDE) ──────────────────
        CreatePartHandler(),
        CreateSketchHandler(),
        SketchHandler(),
        AddCenterRectangleHandler(),
        AddCirclesHandler(),
        ExtrudeBossHandler(),
        ExtrudeCutHandler(),
        RebuildHandler(),
        NoopHandler(),
        DeleteFeatureHandler(),
        # ── Phase 2: DELEGATABLE handlers ────────────────────────────
        HoleWizardHandler(),
        FilletHandler(),
        ChamferHandler(),
        CircularPatternHandler(),
        ShellHandler(),
        # LinearPatternHandler(),    # op_handlers/pattern.py
        # MirrorHandler(),           # op_handlers/pattern.py
    ]
    return {h.op_type: h for h in handlers}


HANDLERS: "dict[str, OpHandler]" = _build_registry()
