"""
Deterministic flanged shaft pattern.

Supported prompt forms:
  "40mm shaft 100mm long"
  "40mm diameter shaft 100mm long with 80mm flange 10mm thick"
  "flanged shaft 40mm OD 100mm long flange 80mm 10mm thick 6 M6 holes 60mm PCD"

OperationGraph emitted:
  sk1 (Front Plane, circle r=flange_r)  → f1 extrude_boss flange_thickness  (flange)
  sk2 (f1 top, circle r=shaft_r)        → f2 extrude_boss shaft_length       (shaft)
  [if bolt_count >= 2]:
    h1  hole_wizard(face_of=f1, positions=[(pcd/2, 0)])
    cp1 circular_pattern(source=[h1], count=bolt_count, pcd=bolt_pcd)

Axes: sketch on Front Plane, +Z is the shaft axis (same convention as SW Copilot).
"""
from __future__ import annotations

import math
import re
from typing import Optional

from models.schemas import (
    CircleEntity,
    CircularPatternOp,
    ExtrudeBossOp,
    HolePosition,
    HoleWizardOp,
    NoopOp,
    OperationGraph,
    SketchOp,
)

# ISO 273 medium series clearance hole diameters (mm) for common bolt sizes
_CLEARANCE = {"M3": 3.4, "M4": 4.5, "M5": 5.5, "M6": 6.6, "M8": 9.0,
              "M10": 11.0, "M12": 13.5, "M16": 17.5, "M20": 22.0}


def generate_flanged_shaft(
    shaft_diameter: float,
    shaft_length: float,
    flange_diameter: float,
    flange_thickness: float,
    bolt_count: int = 0,
    bolt_pcd_mm: float = 0.0,
    bolt_size: str = "M6",
) -> OperationGraph:
    if shaft_diameter <= 0 or shaft_length <= 0:
        return OperationGraph(
            operations=[NoopOp(id="n1", message="Shaft diameter and length must be positive.")],
            missing_inputs=["shaft diameter (mm)", "shaft length (mm)"],
        )
    if flange_diameter <= shaft_diameter:
        return OperationGraph(
            operations=[NoopOp(id="n1", message=(
                f"Flange diameter ({flange_diameter}mm) must be larger than "
                f"shaft diameter ({shaft_diameter}mm)."
            ))],
            missing_inputs=["flange diameter > shaft diameter"],
        )
    if flange_thickness <= 0:
        return OperationGraph(
            operations=[NoopOp(id="n1", message="Flange thickness must be positive.")],
            missing_inputs=["flange thickness (mm)"],
        )

    shaft_r  = shaft_diameter  / 2
    flange_r = flange_diameter / 2

    ops: list = []

    # Flange: circle on Front Plane → extrude_boss flange_thickness
    sk1 = SketchOp(
        id="sk1", plane="Front Plane",
        entities=[CircleEntity(cx_mm=0, cy_mm=0, radius_mm=flange_r)],  # type: ignore
    )
    f1 = ExtrudeBossOp(id="f1", profile_id="sk1", depth_mm=flange_thickness, name="Flange")
    ops.extend([sk1, f1])

    # Shaft: circle on top face of flange → extrude_boss shaft_length
    sk2 = SketchOp(
        id="sk2", plane="f1 top",
        entities=[CircleEntity(cx_mm=0, cy_mm=0, radius_mm=shaft_r)],  # type: ignore
    )
    f2 = ExtrudeBossOp(id="f2", profile_id="sk2", depth_mm=shaft_length, name="Shaft")
    ops.extend([sk2, f2])

    assumptions = [
        f"Shaft axis along +Z (Front Plane extrude convention)",
        f"Shaft Ø{shaft_diameter}mm × {shaft_length}mm long",
        f"Flange Ø{flange_diameter}mm × {flange_thickness}mm thick at base",
        f"Shaft centered at global origin",
    ]

    # Bolt circle on flange face
    if bolt_count >= 2 and bolt_pcd_mm > 0:
        if bolt_pcd_mm >= flange_diameter:
            assumptions.append(
                f"WARNING: bolt PCD {bolt_pcd_mm}mm >= flange OD {flange_diameter}mm — "
                "holes will land outside the flange"
            )
        clearance_d = _CLEARANCE.get(bolt_size.upper(), 6.6)
        h1 = HoleWizardOp(
            id="h1", face_of="f1",
            hole_type="simple", fastener_size=bolt_size.upper(),
            through_all=True, depth_mm=0,
            positions=[HolePosition(x_mm=bolt_pcd_mm / 2, y_mm=0)],
        )
        cp1 = CircularPatternOp(
            id="cp1", source_ids=["h1"],
            count=bolt_count, pcd_mm=bolt_pcd_mm,
        )
        ops.extend([h1, cp1])
        assumptions += [
            f"{bolt_count}× {bolt_size} clearance holes (Ø{clearance_d}mm) on {bolt_pcd_mm}mm PCD",
        ]
    elif bolt_count >= 2:
        assumptions.append("Bolt PCD not specified — bolt holes omitted; follow up with 'add N M6 holes on Xmm PCD'")

    return OperationGraph(
        part_name=f"flanged_shaft_d{shaft_diameter}_l{shaft_length}",
        operations=ops,
        assumptions=assumptions,
        missing_inputs=[],
    )


# ── Natural-language parser ───────────────────────────────────────────────────

_SHAFT_KW = re.compile(
    r"\b(flanged?\s*shaft|shaft|axle|spindle|flanged\s+cylinder)\b", re.I
)

_SHAFT_D_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*mm\s*(?:shaft|dia(?:meter)?|OD|Ø)\b"
    r"|\b(?:shaft|dia(?:meter)?|OD)\s*[=:\s]\s*(\d+(?:\.\d+)?)\s*mm\b",
    re.I,
)
_SHAFT_L_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*mm\s*(?:long|length|tall)\b"
    r"|\b(?:long|length)\s*[=:\s]\s*(\d+(?:\.\d+)?)\s*mm\b",
    re.I,
)
_FLANGE_D_RE = re.compile(
    r"\bflange\s*[=:\s]?\s*(\d+(?:\.\d+)?)\s*mm\b"
    r"|\b(\d+(?:\.\d+)?)\s*mm\s*flange\b",
    re.I,
)
_FLANGE_T_RE = re.compile(
    r"\bflange\s+(?:thickness|thick)\s*[=:\s]?\s*(\d+(?:\.\d+)?)\s*mm\b"
    r"|\b(\d+(?:\.\d+)?)\s*mm\s*(?:flange\s+)?thick\b",
    re.I,
)
_BOLT_N_RE   = re.compile(r"\b(\d+)\s*(?:×|x|\*|bolt|hole|M\d)", re.I)
_BOLT_PCD_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*mm\s*(?:PCD|bolt\s*circle|pitch\s*circle)\b"
    r"|\bPCD\s*[=:\s]\s*(\d+(?:\.\d+)?)\s*mm\b",
    re.I,
)
_BOLT_SZ_RE  = re.compile(r"\b(M\d+)\b", re.I)


def _first(*matches: re.Match | None, groups=(1, 2)) -> float | None:
    for m in matches:
        if m is None:
            continue
        for g in groups:
            try:
                v = m.group(g)
                if v is not None:
                    return float(v)
            except (IndexError, TypeError):
                pass
    return None


def parse_shaft_params(prompt: str) -> dict | None:
    shaft_d  = _first(_SHAFT_D_RE.search(prompt))
    shaft_l  = _first(_SHAFT_L_RE.search(prompt))
    flange_d = _first(_FLANGE_D_RE.search(prompt))
    flange_t = _first(_FLANGE_T_RE.search(prompt))

    if shaft_d is None or shaft_l is None:
        return None  # can't build without shaft OD + length

    bolt_n_m = _BOLT_N_RE.search(prompt)
    bolt_n   = int(bolt_n_m.group(1)) if bolt_n_m else 0
    bolt_pcd = _first(_BOLT_PCD_RE.search(prompt))
    bolt_sz_m = _BOLT_SZ_RE.search(prompt)
    bolt_sz  = bolt_sz_m.group(1).upper() if bolt_sz_m else "M6"

    # Default flange: 2× shaft OD, 10% of shaft length
    if flange_d is None:
        flange_d = shaft_d * 2
    if flange_t is None:
        flange_t = max(10.0, shaft_d * 0.15)

    return {
        "shaft_diameter":   shaft_d,
        "shaft_length":     shaft_l,
        "flange_diameter":  flange_d,
        "flange_thickness": flange_t,
        "bolt_count":       bolt_n,
        "bolt_pcd_mm":      bolt_pcd or 0.0,
        "bolt_size":        bolt_sz,
    }


def try_generate_shaft(prompt: str) -> OperationGraph | None:
    if not _SHAFT_KW.search(prompt):
        return None

    params = parse_shaft_params(prompt)
    if params is None:
        return OperationGraph(
            operations=[NoopOp(id="n1", message=(
                "Please specify shaft diameter and length "
                "(e.g. '40mm shaft 100mm long'). "
                "Flange defaults to 2× shaft OD if not given."
            ))],
            missing_inputs=["shaft diameter (mm)", "shaft length (mm)"],
        )

    return generate_flanged_shaft(**params)
