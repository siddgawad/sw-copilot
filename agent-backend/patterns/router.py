"""
Pattern router — deterministic gate before the LLM.

Each registered pattern handler takes (prompt: str) and returns an
OperationGraph when it recognises the request, or None to pass through
to the next handler. If all handlers return None the LLM is called.

Routing order matters: put the most specific patterns first.
"""
from __future__ import annotations

from models.schemas import DocumentContext, OperationGraph
from agents.box_v0 import try_generate as try_generate_box
from agents.cylinder_v0 import try_generate as try_generate_cylinder
from agents.help_v0 import try_generate as try_generate_help
from patterns.flange import try_generate as try_generate_flange
from patterns.followup_features import try_generate as try_generate_followup_features
from patterns.gear import try_generate_gear
from patterns.plate import try_generate as try_generate_plate
from patterns.shaft import try_generate_shaft

_CONTEXT_HANDLERS = [
    try_generate_followup_features,
]

_HANDLERS = [
    try_generate_help,    # must be first — greetings/help before geometry parsers
    try_generate_gear,
    try_generate_flange,  # circular disk + bolt circle — try before cylinder
    try_generate_plate,   # flat rectangular plate — try before box (more specific)
    try_generate_shaft,
    try_generate_box,
    try_generate_cylinder,
    # add: try_generate_bracket, try_generate_bushing, try_generate_spacer, etc.
]


def try_pattern_match(prompt: str, context: DocumentContext | None = None) -> OperationGraph | None:
    """
    Try each registered pattern in priority order.
    Returns the first non-None result, or None if no pattern matched.
    """
    for handler in _CONTEXT_HANDLERS:
        result = handler(prompt, context)
        if result is not None:
            return result

    for handler in _HANDLERS:
        result = handler(prompt)
        if result is not None:
            return result
    return None
