"""Regression tests for _extract_json_object's repair fallback.

Real LLM outputs that broke `json.loads` in production; the repair layer
should rescue each of them without changing the call chain.
"""
from __future__ import annotations

import pytest

from agents.macro_engineer import _extract_json_object


def test_clean_json_parses_unchanged():
    out = _extract_json_object('{"part_name":"plate","operations":[]}')
    assert out["part_name"] == "plate"


def test_fenced_code_block_is_stripped():
    raw = '```json\n{"part_name":"plate","operations":[]}\n```'
    out = _extract_json_object(raw)
    assert out["part_name"] == "plate"


def test_trailing_prose_after_json_is_ignored():
    raw = '{"part_name":"plate","operations":[]}\n\nNote: this is correct.'
    out = _extract_json_object(raw)
    assert out["part_name"] == "plate"


def test_leading_prose_before_json_is_skipped():
    raw = 'Here is your plan:\n\n{"part_name":"plate","operations":[]}'
    out = _extract_json_object(raw)
    assert out["part_name"] == "plate"


def test_trailing_comma_is_repaired():
    raw = '{"part_name":"plate","operations":[],}'
    out = _extract_json_object(raw)
    assert out["part_name"] == "plate"


def test_single_quotes_are_repaired():
    raw = "{'part_name':'plate','operations':[]}"
    out = _extract_json_object(raw)
    assert out["part_name"] == "plate"


def test_jsonc_line_comment_is_repaired():
    raw = '''{
        // a plate
        "part_name": "plate",
        "operations": []
    }'''
    out = _extract_json_object(raw)
    assert out["part_name"] == "plate"


def test_no_json_object_raises_clear_error():
    with pytest.raises(ValueError, match="did not contain a JSON object"):
        _extract_json_object("There is no JSON here at all.")
