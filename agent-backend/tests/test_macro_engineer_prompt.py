# Regression tests for the macro_engineer system prompt and repair-loop
# behaviour. These pin down the LLM contract surface without making any
# Groq API calls — we assert on the prompt strings and the helper functions
# that drive `build_system_prompt`. Any change to the contract that breaks
# these tests must update them deliberately.
#
# Live SolidWorks beta6 surfaced two LLM bugs that motivate this file:
#   1. "circle 30mm" was interpreted as radius -> 60mm-diameter cylinder.
#   2. "50 wide 30 deep 20 tall" had depth and height swapped.
#   3. The repair loop emitted the same broken graph two attempts in a row.

import json

import pytest

from agents.macro_engineer import (
    _COMPACT_REPAIR_ADDENDUM,
    _COMPACT_SYSTEM_PROMPT,
    _ProviderQuotaError,
    _REPAIR_REPETITION_NOTE,
    MacroEngineerAgent,
    _normalize_operations,
    _operations_from_message,
    _repair_loop_repeated,
    build_system_prompt,
)
from models.schemas import ConversationMessage


# ── System prompt contract ────────────────────────────────────────────────────

def test_compact_prompt_contains_circle_diameter_default():
    """Bug 1: bare 'Nmm circle' must default to diameter, not radius."""
    assert "DIAMETER" in _COMPACT_SYSTEM_PROMPT
    assert "radius_mm = 15" in _COMPACT_SYSTEM_PROMPT  # for the 30mm example
    # Explicit "radius Nmm" override must still be allowed.
    assert "radius" in _COMPACT_SYSTEM_PROMPT.lower()


def test_compact_prompt_contains_top_plane_axis_mapping():
    """Bug 2: wide/deep/tall must map to fixed axes on Top Plane."""
    assert "AXIS MAPPING" in _COMPACT_SYSTEM_PROMPT
    assert "Top Plane" in _COMPACT_SYSTEM_PROMPT
    assert "wide" in _COMPACT_SYSTEM_PROMPT
    assert "deep" in _COMPACT_SYSTEM_PROMPT
    assert "tall" in _COMPACT_SYSTEM_PROMPT
    # The canonical example must show the right answer for the live bug.
    assert "50mm wide 30mm deep 20mm tall" in _COMPACT_SYSTEM_PROMPT


def test_compact_prompt_contains_front_plane_axis_mapping():
    """Front Plane uses depth as extrude direction, not Y; spell it out."""
    assert "Front Plane" in _COMPACT_SYSTEM_PROMPT
    # All three orientation words on Front Plane must be addressed.
    front_section_idx = _COMPACT_SYSTEM_PROMPT.find("Front Plane")
    front_section = _COMPACT_SYSTEM_PROMPT[front_section_idx:]
    assert "long" in front_section or "length" in front_section


def test_compact_repair_addendum_lists_common_fixes():
    """Live test showed the repair loop didn't know the canonical fix for
    'Could not select top face'. The compact addendum now spells it out."""
    assert "Could not select top face" in _COMPACT_REPAIR_ADDENDUM
    assert "active_top_face" in _COMPACT_REPAIR_ADDENDUM


# ── Repair-mode prompt assembly ───────────────────────────────────────────────

def test_build_system_prompt_no_history_is_clean():
    """No history -> bare prompt, no repair addenda."""
    prompt = build_system_prompt(None)
    assert _COMPACT_REPAIR_ADDENDUM not in prompt
    assert _REPAIR_REPETITION_NOTE not in prompt


def test_build_system_prompt_with_error_appends_repair():
    history = [
        ConversationMessage(role="user", content="add holes"),
        ConversationMessage(role="assistant", content="Runtime: ERROR: Could not select top face"),
    ]
    prompt = build_system_prompt(history)
    assert _COMPACT_REPAIR_ADDENDUM in prompt
    # Single failure -> no repetition note yet.
    assert _REPAIR_REPETITION_NOTE not in prompt


def test_build_system_prompt_appends_repetition_note_on_loop():
    """Two assistant turns with structurally identical operations must
    trigger the stronger 'do not regenerate the same graph' note."""
    failing_graph = json.dumps({
        "operations": [
            {"id": "sk1", "type": "sketch", "plane": "Top Plane",
             "entities": [{"type": "rectangle", "x1_mm": -25, "y1_mm": -15, "x2_mm": 25, "y2_mm": 15}]},
            {"id": "f1", "type": "extrude_boss", "profile_id": "sk1", "depth_mm": 20},
            {"id": "h1", "type": "hole_wizard", "face_of": "ex1", "fastener_size": "M6",
             "hole_type": "counterbore", "through_all": True, "depth_mm": 0,
             "positions": [{"x_mm": -15, "y_mm": -10}]},
        ],
    })
    repaired_graph = json.dumps({
        "operations": [
            # Same shape, different ids — should still register as repeat.
            {"id": "sk2", "type": "sketch", "plane": "Top Plane",
             "entities": [{"type": "rectangle", "x1_mm": -25, "y1_mm": -15, "x2_mm": 25, "y2_mm": 15}]},
            {"id": "f2", "type": "extrude_boss", "profile_id": "sk2", "depth_mm": 20},
            {"id": "h2", "type": "hole_wizard", "face_of": "ex1", "fastener_size": "M6",
             "hole_type": "counterbore", "through_all": True, "depth_mm": 0,
             "positions": [{"x_mm": -15, "y_mm": -10}]},
        ],
    })
    history = [
        ConversationMessage(role="user", content="add holes"),
        ConversationMessage(role="assistant", content=failing_graph),
        ConversationMessage(role="user", content="that failed"),
        ConversationMessage(role="assistant",
                            content=repaired_graph + "\nRuntime: ERROR: Could not select top face of 'ex1'"),
    ]
    prompt = build_system_prompt(history)
    assert _COMPACT_REPAIR_ADDENDUM in prompt
    assert _REPAIR_REPETITION_NOTE in prompt


def test_build_system_prompt_no_repetition_when_graph_changed():
    """If the LLM actually changed the graph between attempts, the stronger
    repetition note must NOT fire (we don't want to over-pressure)."""
    first = json.dumps({
        "operations": [
            {"id": "h1", "type": "hole_wizard", "face_of": "ex1", "fastener_size": "M6",
             "hole_type": "counterbore", "through_all": True, "depth_mm": 0,
             "positions": [{"x_mm": -15, "y_mm": -10}]},
        ],
    })
    second = json.dumps({
        "operations": [
            {"id": "h1", "type": "hole_wizard", "face_of": "Top Plane", "fastener_size": "M6",
             "hole_type": "counterbore", "through_all": True, "depth_mm": 0,
             "positions": [{"x_mm": -15, "y_mm": -10}]},
        ],
    })
    history = [
        ConversationMessage(role="assistant", content=first + "\nRuntime: ERROR"),
        ConversationMessage(role="assistant", content=second + "\nRuntime: ERROR: still bad"),
    ]
    prompt = build_system_prompt(history)
    assert _COMPACT_REPAIR_ADDENDUM in prompt
    assert _REPAIR_REPETITION_NOTE not in prompt


# ── Operation normalisation helpers ───────────────────────────────────────────

def test_normalize_operations_strips_ids_and_names():
    a = [{"id": "f1", "name": "Boss", "type": "extrude_boss",
          "profile_id": "sk1", "depth_mm": 20}]
    b = [{"id": "f99", "name": "Different Name", "type": "extrude_boss",
          "profile_id": "sk2", "depth_mm": 20}]
    assert _normalize_operations(a) == _normalize_operations(b)


def test_normalize_operations_preserves_meaningful_diffs():
    a = [{"id": "f1", "type": "extrude_boss", "profile_id": "sk1", "depth_mm": 20}]
    b = [{"id": "f1", "type": "extrude_boss", "profile_id": "sk1", "depth_mm": 30}]
    assert _normalize_operations(a) != _normalize_operations(b)


def test_normalize_operations_normalises_source_id_lists():
    a = [{"id": "fi1", "type": "fillet", "feature_ids": ["f1", "f2"], "radius_mm": 2}]
    b = [{"id": "fi1", "type": "fillet", "feature_ids": ["f99", "f100"], "radius_mm": 2}]
    assert _normalize_operations(a) == _normalize_operations(b)


def test_normalize_operations_handles_garbage_input():
    assert _normalize_operations([]) == []
    assert _normalize_operations(None) == []  # type: ignore[arg-type]
    assert _normalize_operations("not a list") == []  # type: ignore[arg-type]


def test_operations_from_message_extracts_embedded_json():
    msg = 'Plan ready.\n{"operations":[{"id":"f1","type":"noop","message":"hi"}]}\nRuntime: ok'
    ops = _operations_from_message(msg)
    assert ops == [{"id": "f1", "type": "noop", "message": "hi"}]


def test_operations_from_message_returns_none_when_absent():
    assert _operations_from_message("just text") is None
    assert _operations_from_message('{"no_operations": true}') is None


# ── Repair-loop detector ──────────────────────────────────────────────────────

def test_repair_loop_repeated_false_with_no_history():
    assert _repair_loop_repeated(None) is False
    assert _repair_loop_repeated([]) is False


def test_repair_loop_repeated_false_with_one_assistant_turn():
    history = [ConversationMessage(role="assistant", content='{"operations":[]}')]
    assert _repair_loop_repeated(history) is False


def test_repair_loop_repeated_true_for_id_only_diff():
    g = lambda i: json.dumps({"operations": [
        {"id": f"f{i}", "type": "extrude_boss", "profile_id": "sk1", "depth_mm": 20},
    ]})
    history = [
        ConversationMessage(role="user", content="x"),
        ConversationMessage(role="assistant", content=g(1)),
        ConversationMessage(role="user", content="failed"),
        ConversationMessage(role="assistant", content=g(2)),
    ]
    assert _repair_loop_repeated(history) is True


def test_repair_loop_repeated_false_when_face_of_switched_to_standard_plane():
    """Switching face_of from an invented feature id to a standard plane
    name is the *canonical* repair — the detector must NOT flag it as a loop."""
    a = json.dumps({"operations": [
        {"id": "h1", "type": "hole_wizard", "face_of": "ex1", "fastener_size": "M6",
         "hole_type": "counterbore", "through_all": True, "depth_mm": 0,
         "positions": [{"x_mm": 0, "y_mm": 0}]},
    ]})
    b = json.dumps({"operations": [
        {"id": "h1", "type": "hole_wizard", "face_of": "Top Plane", "fastener_size": "M6",
         "hole_type": "counterbore", "through_all": True, "depth_mm": 0,
         "positions": [{"x_mm": 0, "y_mm": 0}]},
    ]})
    history = [
        ConversationMessage(role="assistant", content=a),
        ConversationMessage(role="assistant", content=b),
    ]
    assert _repair_loop_repeated(history) is False


def test_repair_loop_repeated_true_when_both_faces_are_invented_ids():
    """Two invented feature ids should still canonicalise the same — that
    *is* a real loop and we want to break out of it."""
    a = json.dumps({"operations": [
        {"id": "h1", "type": "hole_wizard", "face_of": "ex1", "fastener_size": "M6",
         "hole_type": "counterbore", "through_all": True, "depth_mm": 0,
         "positions": [{"x_mm": 0, "y_mm": 0}]},
    ]})
    b = json.dumps({"operations": [
        {"id": "h1", "type": "hole_wizard", "face_of": "f99", "fastener_size": "M6",
         "hole_type": "counterbore", "through_all": True, "depth_mm": 0,
         "positions": [{"x_mm": 0, "y_mm": 0}]},
    ]})
    history = [
        ConversationMessage(role="assistant", content=a),
        ConversationMessage(role="assistant", content=b),
    ]
    assert _repair_loop_repeated(history) is True


@pytest.mark.parametrize("changed_field,new_value", [
    ("depth_mm", 30),       # changed depth
    ("type", "extrude_cut"),  # changed op type
])
def test_repair_loop_repeated_false_when_real_field_changed(changed_field, new_value):
    base = {"id": "f1", "type": "extrude_boss", "profile_id": "sk1", "depth_mm": 20}
    a = json.dumps({"operations": [base]})
    b = json.dumps({"operations": [{**base, changed_field: new_value}]})
    history = [
        ConversationMessage(role="assistant", content=a),
        ConversationMessage(role="assistant", content=b),
    ]
    assert _repair_loop_repeated(history) is False


def test_provider_router_falls_back_after_quota(monkeypatch):
    agent = MacroEngineerAgent.__new__(MacroEngineerAgent)
    agent._provider = "nim"
    agent._fallbacks = ["ollama"]
    calls = []

    def fake_call(provider, messages):
        calls.append(provider)
        if provider == "nim":
            raise _ProviderQuotaError("nim quota")
        return '{"operations":[{"id":"noop1","type":"noop","message":"ok"}]}'

    monkeypatch.setattr(agent, "_call_provider", fake_call)

    assert "noop1" in agent._call_with_fallback([])
    assert calls == ["nim", "ollama"]


def test_provider_router_reports_all_unavailable(monkeypatch):
    agent = MacroEngineerAgent.__new__(MacroEngineerAgent)
    agent._provider = "nim"
    agent._fallbacks = ["ollama", "groq"]

    def fake_call(provider, messages):
        raise _ProviderQuotaError(f"{provider} unavailable")

    monkeypatch.setattr(agent, "_call_provider", fake_call)

    with pytest.raises(Exception, match="All LLM providers are unavailable"):
        agent._call_with_fallback([])
