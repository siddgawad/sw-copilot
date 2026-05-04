"""
Deterministic spur gear pattern library.

Architecture note:
  This module is the "compiler" layer for gear geometry.  The LLM is bypassed
  entirely.  The caller asks "what does the user want?" and this module answers
  "here is the exact involute polygon for SolidWorks."

Geometry:
  Standard external spur gear, ISO 53 profile.
  Tooth flanks are approximated as 12-point involute polylines.
  Tip and root transitions are approximated as 4-segment circular arcs.
  The full closed profile is emitted as LineEntity objects in one SketchOp,
  followed by an ExtrudeBossOp for the face width.

Limitations (add to user message):
  - Helical angle not implemented (emit a note).
  - Hub bore not generated; user can follow up with "add a 20mm bore".
  - Undercut relief not modelled when r_dedendum < r_base (most small gears
    with few teeth); the flank simply starts from the base circle.
"""
from __future__ import annotations

import math
import re
from typing import Optional

from models.schemas import (
    ExtrudeBossOp,
    LineEntity,
    NoopOp,
    OperationGraph,
    SketchOp,
)

# ── Math primitives ───────────────────────────────────────────────────────────

def _inv_xy(r_b: float, t: float) -> tuple[float, float]:
    """(x, y) on the involute of base circle r_b at unroll parameter t."""
    return (r_b * (math.cos(t) + t * math.sin(t)),
            r_b * (math.sin(t) - t * math.cos(t)))


def _t_for_r(r_b: float, r: float) -> float:
    """Unroll parameter t where the involute point lies on circle r."""
    if r <= r_b:
        return 0.0
    return math.sqrt((r / r_b) ** 2 - 1)


def _rot(x: float, y: float, a: float) -> tuple[float, float]:
    c, s = math.cos(a), math.sin(a)
    return c * x - s * y, s * x + c * y


def _mirror_about_angle(x: float, y: float, center_angle: float) -> tuple[float, float]:
    """Mirror point (x, y) across the ray at angle center_angle through origin."""
    x2, y2 = _rot(x, y, -center_angle)
    return _rot(x2, -y2, center_angle)  # negate y then rotate back


def _arc_pts(r: float, a_start: float, a_end: float, n: int) -> list[tuple[float, float]]:
    """n interpolated points along a CCW arc (not including a_start, including a_end)."""
    while a_end < a_start:
        a_end += 2 * math.pi
    return [
        (r * math.cos(a_start + (a_end - a_start) * k / n),
         r * math.sin(a_start + (a_end - a_start) * k / n))
        for k in range(1, n + 1)
    ]


# ── Core profile generator ────────────────────────────────────────────────────

_N_INV  = 12   # involute samples per flank
_N_TIP  = 4    # tip arc segments per tooth
_N_ROOT = 4    # root arc segments between teeth


def _gear_profile_mm(
    teeth: int,
    module: float,
    pressure_angle_deg: float,
) -> list[tuple[float, float]]:
    """
    Return a closed CCW polygon (list of (x_mm, y_mm)) for an external spur gear.

    Traversal order per tooth:
      right_flank (root→tip) → tip_arc (right→left) → left_flank (tip→root)
      → root_arc (this left-root → next right-root)
    """
    N   = teeth
    m   = module
    phi = math.radians(pressure_angle_deg)

    r_p = m * N / 2                                # pitch radius
    r_b = r_p * math.cos(phi)                      # base radius
    r_a = r_p + m                                  # addendum radius
    r_d = max(r_p - 1.25 * m, r_b)                # dedendum radius (clamped to base)

    tooth_angle = 2 * math.pi / N
    half_tooth  = math.pi / (2 * N)               # half-pitch at pitch circle

    # Angular position of the involute point at t=phi (on the pitch circle)
    _x0, _y0 = _inv_xy(r_b, phi)
    inv_angle_at_pitch = math.atan2(_y0, _x0)

    # Rotation so the right flank is centred correctly for tooth at angle 0:
    # at pitch circle the right flank should sit at angle -half_tooth
    right_rot0 = -half_tooth - inv_angle_at_pitch

    t_start = _t_for_r(r_b, r_d)
    t_end   = _t_for_r(r_b, r_a)

    profile: list[tuple[float, float]] = []

    for i in range(N):
        theta = i * tooth_angle          # this tooth's centre angle
        right_rot = right_rot0 + theta   # combined rotation for this tooth

        # ── right flank (root → tip) ──────────────────────────────────────────
        right_pts: list[tuple[float, float]] = []
        for j in range(_N_INV):
            t   = t_start + (t_end - t_start) * j / (_N_INV - 1)
            x,y = _inv_xy(r_b, t)
            right_pts.append(_rot(x, y, right_rot))

        # ── tip arc (right tip → left tip, CCW at addendum radius) ───────────
        rt = right_pts[-1]
        a_rt = math.atan2(rt[1], rt[0])
        a_lt = 2 * theta - a_rt          # mirror angle across tooth centre

        profile.extend(right_pts)
        profile.extend(_arc_pts(r_a, a_rt, a_lt, _N_TIP))

        # ── left flank (left tip → root) — mirror of right, reversed ─────────
        for j in range(_N_INV - 1, -1, -1):
            rx, ry = right_pts[j]
            profile.append(_mirror_about_angle(rx, ry, theta))

        # ── root arc (left root → right root of next tooth, CCW) ─────────────
        lroot = profile[-1]
        a_lr = math.atan2(lroot[1], lroot[0])

        next_theta = (i + 1) * tooth_angle
        x0, y0 = _inv_xy(r_b, t_start)
        next_rr  = _rot(x0, y0, right_rot0 + next_theta)
        a_rr = math.atan2(next_rr[1], next_rr[0])

        profile.extend(_arc_pts(r_d, a_lr, a_rr, _N_ROOT))

    return profile


# ── OperationGraph builder ────────────────────────────────────────────────────

def generate_spur_gear(
    teeth: int,
    module: float,
    pressure_angle_deg: float = 20.0,
    thickness_mm: float = 10.0,
) -> OperationGraph:
    """
    Build a deterministic OperationGraph for an external spur gear.

    Schema: sketch (Front Plane, involute polygon) + extrude_boss (thickness_mm).
    The LLM is never called.
    """
    if teeth < 5:
        return OperationGraph(
            operations=[NoopOp(id="n1", message=(
                f"Gear requires at least 5 teeth (requested {teeth}). "
                "Fewer than 5 teeth produces severe undercutting and is not manufacturable."
            ))],
            missing_inputs=["number of teeth (N >= 5)"],
        )
    if module <= 0:
        return OperationGraph(
            operations=[NoopOp(id="n1", message="Module must be > 0 mm.")],
            missing_inputs=["module (positive number, e.g. m2 = 2mm tooth size)"],
        )
    if thickness_mm <= 0:
        return OperationGraph(
            operations=[NoopOp(id="n1", message="Face width (thickness) must be > 0 mm.")],
            missing_inputs=["face width / thickness in mm"],
        )

    profile = _gear_profile_mm(teeth, module, pressure_angle_deg)

    lines: list[LineEntity] = []
    n = len(profile)
    for j in range(n):
        x1, y1 = profile[j]
        x2, y2 = profile[(j + 1) % n]
        lines.append(LineEntity(
            x1_mm=round(x1, 4), y1_mm=round(y1, 4),
            x2_mm=round(x2, 4), y2_mm=round(y2, 4),
        ))

    r_p = module * teeth / 2
    r_a = r_p + module
    r_d = max(r_p - 1.25 * module, r_p * math.cos(math.radians(pressure_angle_deg)))

    sk = SketchOp(id="sk1", plane="Front Plane", entities=lines)  # type: ignore[arg-type]
    ex = ExtrudeBossOp(id="f1", profile_id="sk1", depth_mm=thickness_mm, name="Gear")

    return OperationGraph(
        part_name=f"spur_gear_{teeth}T_m{module}",
        operations=[sk, ex],
        assumptions=[
            f"ISO 53 standard involute profile, external spur gear",
            f"Module m={module} mm, N={teeth} teeth, pressure angle φ={pressure_angle_deg}°",
            f"Pitch diameter = {2*r_p:.2f} mm, addendum diameter = {2*r_a:.2f} mm",
            f"Face width (extrude depth) = {thickness_mm} mm",
            f"No hub bore — follow up with 'add a Xmm bore at centre' if needed",
            f"No helical angle — spur teeth only; helical requires macro path",
        ] + (
            [f"Dedendum clamped to base circle r_b={r_d:.2f} mm — undercut relief not modelled"]
            if r_p - 1.25 * module < r_p * math.cos(math.radians(pressure_angle_deg))
            else []
        ),
        missing_inputs=[],
    )


# ── Natural-language parser ───────────────────────────────────────────────────

_GEAR_KW = re.compile(r"\b(gear|spur\s*gear|helical\s*gear|pinion|cog)\b", re.I)

_TEETH_RE    = re.compile(r"\b(\d+)\s*[-–]?\s*(?:teeth|tooth|T\b)", re.I)
_MODULE_RE   = re.compile(
    r"\bm\s*=?\s*(\d+(?:\.\d+)?)\b"         # m2, m=2, m=2.5
    r"|\b(\d+(?:\.\d+)?)\s*mm?\s*module\b"  # 2mm module
    r"|\bmodule\s*[=:\s]\s*(\d+(?:\.\d+)?)\b",  # module=2
    re.I,
)
_PA_RE       = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(?:degree|deg|°).*?pressure"
    r"|pressure.*?\b(\d+(?:\.\d+)?)\s*(?:degree|deg|°)"
    r"|\bPA\s*[=:\s]\s*(\d+(?:\.\d+)?)\b",
    re.I,
)
_THICK_RE    = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*mm\s*(?:thick|face\s*width|width|wide|depth|deep)\b"
    r"|\bface\s*width\s*[=:\s]\s*(\d+(?:\.\d+)?)\s*mm\b",
    re.I,
)


def _extract_first(m: re.Match | None, *groups: int) -> float | None:
    if m is None:
        return None
    for g in groups:
        try:
            v = m.group(g)
            if v is not None:
                return float(v)
        except (IndexError, TypeError):
            pass
    return None


def parse_gear_params(prompt: str) -> dict | None:
    """
    Extract gear parameters from natural language.
    Returns a dict suitable for generate_spur_gear(), or None if teeth count
    cannot be determined (caller should return a noop asking for it).
    """
    teeth  = _extract_first(_TEETH_RE.search(prompt), 1)
    module = _extract_first(_MODULE_RE.search(prompt), 1, 2, 3)
    pa     = _extract_first(_PA_RE.search(prompt), 1, 2, 3)
    thick  = _extract_first(_THICK_RE.search(prompt), 1, 2)

    if teeth is None:
        return None  # can't build without teeth count

    return {
        "teeth":               int(teeth),
        "module":              module or 2.0,
        "pressure_angle_deg":  pa    or 20.0,
        "thickness_mm":        thick or 10.0,
    }


def try_generate_gear(prompt: str) -> OperationGraph | None:
    """
    Entry point for the pattern router.

    Returns an OperationGraph when the prompt clearly describes a gear.
    Returns None when the prompt is not about a gear (let the LLM handle it).
    """
    if not _GEAR_KW.search(prompt):
        return None

    params = parse_gear_params(prompt)
    if params is None:
        return OperationGraph(
            operations=[NoopOp(id="n1", message=(
                "Please specify the number of teeth (e.g. '20 teeth'), "
                "module (e.g. 'm2'), and face width (e.g. '10mm thick'). "
                "Pressure angle defaults to 20° (ISO standard) if not specified."
            ))],
            missing_inputs=["number of teeth", "module (tooth size)"],
        )

    return generate_spur_gear(**params)
