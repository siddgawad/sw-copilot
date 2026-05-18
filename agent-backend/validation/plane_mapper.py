"""Map sketch-plane string identifiers to build123d Plane instances.

The OperationGraph uses SolidWorks-style plane names ("Front Plane",
"Top Plane", "Right Plane"). build123d uses its own Plane class. This
module is the single point of translation so handlers never branch on
plane strings themselves.

Coordinate convention (must match the rest of sw-copilot):
    Front Plane → XY (extrudes in +Z)
    Top Plane   → XZ (extrudes in +Y)
    Right Plane → YZ (extrudes in +X)

See CLAUDE.md and patterns/plate.py for the rationale on Front Plane
being the default for flat parts.
"""
from __future__ import annotations

from build123d import Plane


_PLANE_MAP: dict[str, Plane] = {
    "front plane": Plane.XY,
    "top plane":   Plane.XZ,
    "right plane": Plane.YZ,
    # Common LLM variants — we accept them defensively rather than coerce
    # the LLM. Saves a repair-loop trip.
    "front":       Plane.XY,
    "top":         Plane.XZ,
    "right":       Plane.YZ,
    "xy":          Plane.XY,
    "xz":          Plane.XZ,
    "yz":          Plane.YZ,
}


def resolve_plane(name: str | None) -> Plane:
    """Return the build123d Plane for a string identifier.

    Falls back to Plane.XY (Front Plane) when None or unknown so handlers
    can always proceed — but logs the unknown name through the caller's
    error channel by raising.

    Raises
    ------
    KeyError
        If `name` is non-empty and not a recognised plane.
    """
    if not name:
        return Plane.XY
    key = name.strip().lower()
    if key not in _PLANE_MAP:
        raise KeyError(
            f"Unknown sketch plane: {name!r}. "
            f"Expected one of: Front Plane, Top Plane, Right Plane."
        )
    return _PLANE_MAP[key]
