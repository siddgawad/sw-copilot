"""
Compound feature appender — extracts trailing fillet/chamfer clauses from a
prompt and appends the corresponding ops to a base OperationGraph.

Example:
  "create a 100x60x10mm plate with 4 M6 holes at corners and 2mm fillet on all edges"
   ^                                                       ^
   |  base shape recognised by plate.py                     |
   +-------------------------------------------------------+--- this module

Each helper returns a *new* operations list. Callers should plug the returned
ops into the graph just before the final 'rebuild' op (or after the holes if
applicable).
"""
from __future__ import annotations

import re

_FILLET_PATTERN = re.compile(
    r"\b(?:and\s+|with\s+|plus\s+)?"
    r"(?:a\s+|an\s+)?"
    r"(\d+(?:\.\d+)?)\s*mm\s+"
    r"(?:radius\s+)?fillet"
    r"(?:\s+(?:on\s+(?:all\s+|external\s+)?edges|all\s+around|everywhere))?",
    re.IGNORECASE,
)
_CHAMFER_PATTERN = re.compile(
    r"\b(?:and\s+|with\s+|plus\s+)?"
    r"(?:a\s+|an\s+)?"
    r"(\d+(?:\.\d+)?)\s*mm\s+chamfer"
    r"(?:\s+on\s+(?:the\s+)?(top|all)\s+edges)?",
    re.IGNORECASE,
)


def extract_fillet_radius_mm(prompt: str) -> float | None:
    m = _FILLET_PATTERN.search(prompt)
    if not m:
        return None
    return float(m.group(1))


def extract_chamfer_distance_mm(prompt: str) -> tuple[float, str] | None:
    """Return (distance_mm, scope) where scope is 'top' or 'all'."""
    m = _CHAMFER_PATTERN.search(prompt)
    if not m:
        return None
    distance = float(m.group(1))
    scope = (m.group(2) or "all").lower()
    return distance, scope


def append_compound_features(
    operations: list[dict],
    prompt: str,
    next_id_seed: int = 1,
) -> list[dict]:
    """Append fillet and chamfer ops if the prompt mentions them.

    Strategy:
      - Find the 'rebuild' op (last op of the base shape).
      - Insert fillet / chamfer ops BEFORE the rebuild so they apply to
        already-built features.
      - If no rebuild op exists, append at the end and add a rebuild.

    Returns the new operations list. Does not mutate the input.
    """
    result = list(operations)
    rebuild_idx = next(
        (i for i, op in enumerate(result) if op.get("type") == "rebuild"),
        None,
    )
    insert_at = rebuild_idx if rebuild_idx is not None else len(result)

    radius = extract_fillet_radius_mm(prompt)
    if radius is not None and radius > 0:
        fillet_op = {
            "id":          f"fi{next_id_seed}",
            "type":        "fillet",
            "feature_ids": [],   # empty = all edges
            "radius_mm":   radius,
        }
        result.insert(insert_at, fillet_op)
        insert_at += 1
        next_id_seed += 1

    chamfer_spec = extract_chamfer_distance_mm(prompt)
    if chamfer_spec is not None:
        distance, scope = chamfer_spec
        if distance > 0:
            feature_ids = ["__top_edges__"] if scope == "top" else []
            chamfer_op = {
                "id":           f"ch{next_id_seed}",
                "type":         "chamfer",
                "feature_ids":  feature_ids,
                "distance_mm":  distance,
            }
            result.insert(insert_at, chamfer_op)
            insert_at += 1

    # Ensure a rebuild is at the very end.
    if rebuild_idx is None and not any(op.get("type") == "rebuild" for op in result):
        result.append({"id": "rb_compound", "type": "rebuild"})

    return result
