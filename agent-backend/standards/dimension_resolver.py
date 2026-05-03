"""
Deterministic standards dimension resolver.

Vector search is unsuitable for exact dimensional data — cosine distance
does not know ISO 273. This module provides sub-millisecond exact lookups
from hardcoded authoritative tables. Every returned value includes a source_ref
that the LLM must propagate into the operation graph.

Sources:
  ISO 273:2003  — Fasteners; clearance holes for bolts and screws
  ISO 4762:2004 — Hexagon socket head cap screws
  ISO 10642:2004 — Hexagon socket countersunk head screws
  ISO 4032:2012 — Hexagon nuts, style 1
  DIN 332-2     — Centre holes
"""

from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class ClearanceHole:
    nominal: str        # e.g. "M6"
    close_mm: float     # ISO 273 close fit
    normal_mm: float    # ISO 273 normal/medium fit  ← use this as default
    loose_mm: float     # ISO 273 loose fit
    standard: str = "ISO 273"


@dataclass(frozen=True)
class CounterboreData:
    nominal: str
    cbore_diameter_mm: float    # counterbore (socket head cap screw)
    cbore_depth_mm: float       # full head height, ISO 4762
    csink_diameter_mm: float    # 90° countersink, ISO 10642
    standard: str = "ISO 4762 / ISO 10642"


@dataclass(frozen=True)
class EdgeInset:
    nominal: str
    inset_mm: float    # standard edge distance from hole centre to part edge
    note: str = "2× clearance hole diameter (standard engineering practice)"


@dataclass(frozen=True)
class TapDrill:
    nominal: str
    drill_mm: float
    pitch_mm: float
    min_engagement_steel_mm: float
    min_engagement_alum_mm: float
    standard: str = "ISO 724 / ISO 965"


# ── ISO 273 clearance holes ───────────────────────────────────────────────────

_CLEARANCE: dict[str, ClearanceHole] = {
    k.nominal: k for k in [
        ClearanceHole("M1.6", 1.7,  1.8,  2.0),
        ClearanceHole("M2",   2.2,  2.4,  2.6),
        ClearanceHole("M2.5", 2.7,  2.9,  3.1),
        ClearanceHole("M3",   3.2,  3.4,  3.6),
        ClearanceHole("M4",   4.3,  4.5,  4.8),
        ClearanceHole("M5",   5.3,  5.5,  5.8),
        ClearanceHole("M6",   6.4,  6.6,  7.0),
        ClearanceHole("M8",   8.4,  9.0,  10.0),
        ClearanceHole("M10",  10.5, 11.0, 12.0),
        ClearanceHole("M12",  13.0, 13.5, 14.5),
        ClearanceHole("M14",  15.0, 15.5, 16.5),
        ClearanceHole("M16",  17.0, 17.5, 18.5),
        ClearanceHole("M18",  19.0, 20.0, 21.0),
        ClearanceHole("M20",  21.0, 22.0, 24.0),
        ClearanceHole("M22",  23.0, 24.0, 26.0),
        ClearanceHole("M24",  25.0, 26.0, 28.0),
        ClearanceHole("M27",  28.0, 30.0, 32.0),
        ClearanceHole("M30",  31.0, 33.0, 35.0),
    ]
}

# ── ISO 4762 counterbores / ISO 10642 countersinks ────────────────────────────

_COUNTERBORE: dict[str, CounterboreData] = {
    k.nominal: k for k in [
        CounterboreData("M2",   4.4,  2.0,  4.40),
        CounterboreData("M2.5", 5.4,  2.5,  5.50),
        CounterboreData("M3",   6.5,  3.0,  6.72),
        CounterboreData("M4",   8.0,  4.0,  8.96),
        CounterboreData("M5",   9.5,  5.0,  11.20),
        CounterboreData("M6",   11.0, 6.0,  13.44),
        CounterboreData("M8",   14.0, 8.0,  17.92),
        CounterboreData("M10",  17.5, 10.0, 22.40),
        CounterboreData("M12",  20.0, 12.0, 26.88),
        CounterboreData("M14",  23.0, 14.0, 30.80),
        CounterboreData("M16",  26.0, 16.0, 35.72),
        CounterboreData("M18",  29.0, 18.0, 39.90),
        CounterboreData("M20",  33.0, 20.0, 44.80),
        CounterboreData("M24",  40.0, 24.0, 53.76),
    ]
}

# ── Standard edge insets (2× clearance hole diameter) ─────────────────────────

_EDGE_INSET: dict[str, EdgeInset] = {
    k.nominal: k for k in [
        EdgeInset("M3",  7.0),
        EdgeInset("M4",  9.0),
        EdgeInset("M5",  11.0),
        EdgeInset("M6",  10.0),   # industry convention rounds to 10mm for M6
        EdgeInset("M8",  14.0),
        EdgeInset("M10", 16.0),
        EdgeInset("M12", 20.0),
        EdgeInset("M14", 22.0),
        EdgeInset("M16", 26.0),
        EdgeInset("M20", 32.0),
        EdgeInset("M24", 38.0),
    ]
}

# ── Tap drill sizes and thread engagement ─────────────────────────────────────

_TAP_DRILL: dict[str, TapDrill] = {
    k.nominal: k for k in [
        TapDrill("M2",   1.6,  0.4,  3.0,  4.0),
        TapDrill("M2.5", 2.05, 0.45, 3.75, 5.0),
        TapDrill("M3",   2.5,  0.5,  4.5,  6.0),
        TapDrill("M4",   3.3,  0.7,  6.0,  8.0),
        TapDrill("M5",   4.2,  0.8,  7.5,  10.0),
        TapDrill("M6",   5.0,  1.0,  9.0,  12.0),
        TapDrill("M8",   6.8,  1.25, 12.0, 16.0),
        TapDrill("M10",  8.5,  1.5,  15.0, 20.0),
        TapDrill("M12",  10.2, 1.75, 18.0, 24.0),
        TapDrill("M16",  14.0, 2.0,  24.0, 32.0),
        TapDrill("M20",  17.5, 2.5,  30.0, 40.0),
        TapDrill("M24",  21.0, 3.0,  36.0, 48.0),
    ]
}


# ── Public API ────────────────────────────────────────────────────────────────

def _normalise(size: str) -> str:
    """Normalise 'm6' → 'M6', '6' → 'M6'."""
    s = size.strip()
    if s.isdigit():
        s = "M" + s
    return s.upper()


def resolve_clearance_hole(fastener: str, fit: str = "normal") -> dict | None:
    """
    Returns exact clearance hole diameter from ISO 273.
    fit: 'close' | 'normal' | 'loose'
    Returns None if fastener size is unknown.
    """
    row = _CLEARANCE.get(_normalise(fastener))
    if row is None:
        return None
    diameter = {"close": row.close_mm, "normal": row.normal_mm, "loose": row.loose_mm}.get(fit, row.normal_mm)
    return {
        "fastener": row.nominal,
        "fit": fit,
        "diameter_mm": diameter,
        "source_ref": f"{row.standard}__{row.nominal}__{fit}",
        "standard": row.standard,
    }


def resolve_counterbore(fastener: str) -> dict | None:
    """Returns ISO 4762 socket head cap screw counterbore dimensions."""
    row = _COUNTERBORE.get(_normalise(fastener))
    if row is None:
        return None
    return {
        "fastener": row.nominal,
        "counterbore_diameter_mm": row.cbore_diameter_mm,
        "counterbore_depth_mm": row.cbore_depth_mm,
        "countersink_diameter_mm": row.csink_diameter_mm,
        "source_ref": f"ISO_4762__{row.nominal}__counterbore",
        "standard": row.standard,
    }


def resolve_edge_inset(fastener: str) -> dict | None:
    """Returns the standard edge inset distance for corner/edge-placed holes."""
    row = _EDGE_INSET.get(_normalise(fastener))
    if row is None:
        return None
    return {
        "fastener": row.nominal,
        "inset_mm": row.inset_mm,
        "source_ref": f"design_rule__edge_inset__{row.nominal}",
        "note": row.note,
    }


def resolve_tap_drill(fastener: str) -> dict | None:
    """Returns drill size and minimum thread engagement depths."""
    row = _TAP_DRILL.get(_normalise(fastener))
    if row is None:
        return None
    return {
        "fastener": row.nominal,
        "drill_mm": row.drill_mm,
        "pitch_mm": row.pitch_mm,
        "min_engagement_steel_mm": row.min_engagement_steel_mm,
        "min_engagement_alum_mm": row.min_engagement_alum_mm,
        "source_ref": f"{row.standard}__{row.nominal}__tap",
        "standard": row.standard,
    }


def resolve_all(fastener: str) -> dict:
    """
    Returns everything known about a fastener size in one call.
    Suitable for injecting into the LLM prompt as grounded context.
    """
    size = _normalise(fastener)
    result: dict = {"fastener": size, "resolved": []}

    ch = resolve_clearance_hole(size)
    if ch:
        result["clearance_hole_normal_mm"] = ch["diameter_mm"]
        result["resolved"].append(ch)

    cb = resolve_counterbore(size)
    if cb:
        result["counterbore_diameter_mm"] = cb["counterbore_diameter_mm"]
        result["counterbore_depth_mm"]    = cb["counterbore_depth_mm"]
        result["resolved"].append(cb)

    ei = resolve_edge_inset(size)
    if ei:
        result["standard_edge_inset_mm"] = ei["inset_mm"]
        result["resolved"].append(ei)

    td = resolve_tap_drill(size)
    if td:
        result["tap_drill_mm"]        = td["drill_mm"]
        result["pitch_mm"]            = td["pitch_mm"]
        result["min_engagement_steel_mm"] = td["min_engagement_steel_mm"]
        result["resolved"].append(td)

    return result


def extract_fasteners_from_prompt(prompt: str) -> list[str]:
    """
    Scans the prompt for metric fastener sizes (M3–M30).
    Returns a list of normalised size strings.
    """
    import re
    hits = re.findall(r"\bm\s*(\d+(?:\.\d+)?)\b", prompt, re.IGNORECASE)
    seen: list[str] = []
    for h in hits:
        s = "M" + h
        if s not in seen:
            seen.append(s)
    return seen


def build_standards_context(prompt: str) -> tuple[str, list[str]]:
    """
    Scans prompt for fastener references, resolves all dimensional data,
    and returns (context_block, source_refs) for LLM injection.
    This is the deterministic alternative to vector search for numbers.
    """
    fasteners = extract_fasteners_from_prompt(prompt)
    if not fasteners:
        return "", []

    lines = ["=== RESOLVED STANDARDS DATA (use these exact values) ==="]
    source_refs: list[str] = []

    for f in fasteners:
        data = resolve_all(f)
        if not data.get("resolved"):
            continue
        lines.append(f"\n{f} fastener (from ISO 273 / ISO 4762):")
        if "clearance_hole_normal_mm" in data:
            lines.append(f"  Clearance hole (normal fit): {data['clearance_hole_normal_mm']} mm")
        if "counterbore_diameter_mm" in data:
            lines.append(f"  Counterbore diameter: {data['counterbore_diameter_mm']} mm")
            lines.append(f"  Counterbore depth:    {data['counterbore_depth_mm']} mm")
        if "standard_edge_inset_mm" in data:
            lines.append(f"  Standard edge inset:  {data['standard_edge_inset_mm']} mm")
        if "tap_drill_mm" in data:
            lines.append(f"  Tap drill:            {data['tap_drill_mm']} mm  (pitch {data['pitch_mm']} mm)")
            td = next((r for r in data["resolved"] if "min_engagement_steel_mm" in r), None)
            if td:
                lines.append(f"  Min thread engagement: {td['min_engagement_steel_mm']} mm steel / {td['min_engagement_alum_mm']} mm aluminium")
        for r in data["resolved"]:
            source_refs.append(r["source_ref"])

    if len(lines) == 1:
        return "", []

    lines.append("\nYou MUST use these exact values. Do not round, guess, or recall from training data.")
    return "\n".join(lines), source_refs
