"""Tests for the learn/failure_memory.py self-improvement subsystem."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from learn import failure_memory as fm
from learn.failure_memory import (
    FailureRecord,
    purge_memory,
    record_failure,
    relevant_failures,
    summarize_for_prompt,
)


@pytest.fixture(autouse=True)
def isolated_memory(tmp_path, monkeypatch):
    """Redirect the JSONL store to a temp dir per test so we don't pollute disk."""
    test_dir  = tmp_path / "memory"
    test_path = test_dir / "failures.jsonl"
    monkeypatch.setattr(fm, "_MEMORY_DIR", test_dir)
    monkeypatch.setattr(fm, "_MEMORY_PATH", test_path)
    yield
    # tmp_path is auto-cleaned by pytest


def test_record_failure_writes_line_to_disk():
    rec = record_failure(
        prompt="add four M6 counterbore holes at the corners",
        op_types=["hole_wizard", "rebuild"],
        error_class="CUT_FAILED",
        error_msg="FeatureCut3 returned null on overlapping geometry",
        part_family="followup_feature_v0",
    )
    assert rec.error_class == "CUT_FAILED"
    assert "hole_wizard" in rec.op_types
    assert fm._MEMORY_PATH.exists()
    with fm._MEMORY_PATH.open(encoding="utf-8") as f:
        line = f.readline()
        data = json.loads(line)
    assert data["error_class"] == "CUT_FAILED"
    assert data["part_family"] == "followup_feature_v0"
    assert "counterbore" in data["tokens"]


def test_relevant_failures_returns_similar_prompts():
    record_failure(
        prompt="add four M6 counterbore holes at the corners",
        op_types=["hole_wizard"],
        error_class="CUT_FAILED",
        error_msg="boom",
    )
    record_failure(
        prompt="create a 50mm wide 30mm deep 20mm tall box",
        op_types=["create_part", "extrude_boss"],
        error_class="EXECUTION_FAILED",
        error_msg="other",
    )
    hits = relevant_failures("add four M8 counterbore holes at corners", k=2)
    assert len(hits) == 1
    assert "counterbore" in hits[0].prompt


def test_relevant_failures_filters_below_min_similarity():
    record_failure(
        prompt="fillet the box",
        op_types=["fillet"],
        error_class="FILLET_FAILED",
        error_msg="x",
    )
    # Completely unrelated query — should return nothing.
    hits = relevant_failures("export to PDF", k=3, min_similarity=0.25)
    assert hits == []


def test_summarize_for_prompt_renders_compact_block():
    rec = FailureRecord.from_failure(
        prompt="shell the box",
        op_types=["shell", "rebuild"],
        error_class="SHELL_FAILED",
        error_msg="wall too thin for steel",
        part_family="",
    )
    block = summarize_for_prompt([rec])
    assert "PAST FAILURES" in block
    assert "shell" in block
    assert "SHELL_FAILED" in block


def test_summarize_for_prompt_returns_empty_when_no_failures():
    assert summarize_for_prompt([]) == ""


def test_purge_memory_clears_file():
    record_failure("p1", ["a"], "X", "y")
    record_failure("p2", ["b"], "X", "y")
    removed = purge_memory()
    assert removed == 2
    assert not fm._MEMORY_PATH.exists()


def test_tokens_drop_stopwords():
    rec = FailureRecord.from_failure(
        prompt="add a fillet to the box",
        op_types=[],
        error_class="X",
        error_msg="y",
    )
    assert "the" not in rec.tokens
    assert "a" not in rec.tokens
    assert "fillet" in rec.tokens
    assert "box" in rec.tokens


def test_record_truncates_long_inputs():
    long_prompt = "x" * 2000
    long_msg = "y" * 2000
    rec = record_failure(long_prompt, [], "X", long_msg)
    assert len(rec.prompt) <= 512
    assert len(rec.error_msg) <= 512
