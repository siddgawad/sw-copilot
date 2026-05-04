"""
Pattern router — deterministic gate before the LLM.

Each registered pattern handler takes (prompt: str) and returns an
OperationGraph when it recognises the request, or None to pass through
to the next handler. If all handlers return None the LLM is called.

Routing order matters: put the most specific patterns first.
"""
from __future__ import annotations

from models.schemas import OperationGraph
from patterns.gear import try_generate_gear

_HANDLERS = [
    try_generate_gear,
    # add: try_generate_spring, try_generate_v_belt_pulley, etc.
]


def try_pattern_match(prompt: str) -> OperationGraph | None:
    """
    Try each registered pattern in priority order.
    Returns the first non-None result, or None if no pattern matched.
    """
    for handler in _HANDLERS:
        result = handler(prompt)
        if result is not None:
            return result
    return None
