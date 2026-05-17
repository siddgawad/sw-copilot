"""Tests for the production-grade failure memory (learn/failure_memory.py).

Covers:
  - basic record + retrieve
  - similarity threshold filtering
  - PII / secret scrubbing
  - atomic write + corruption recovery
  - deduplication within the dedup window
  - bounded growth (eviction at MAX_RECORDS)
  - prompt summarisation
  - purge + stats
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from learn import failure_memory as fm
from learn.failure_memory import (
    FailureRecord,
    SCHEMA_VERSION,
    memory_stats,
    purge_memory,
    record_failure,
    relevant_failures,
    summarize_for_prompt,
    _reset_cache_for_tests,
)


@pytest.fixture(autouse=True)
def isolated_memory(tmp_path, monkeypatch):
    """Redirect storage + reset cache per test so we don't pollute disk."""
    test_dir  = tmp_path / "memory"
    test_path = test_dir / "failures.jsonl"
    monkeypatch.setattr(fm, "_MEMORY_DIR", test_dir)
    monkeypatch.setattr(fm, "_MEMORY_PATH", test_path)
    _reset_cache_for_tests()
    yield
    _reset_cache_for_tests()


# ── Basic record + retrieve ───────────────────────────────────────────────────

def test_record_failure_writes_atomic_jsonl():
    rec = record_failure(
        prompt="add four M6 counterbore holes at the corners",
        op_types=["hole_wizard", "rebuild"],
        error_class="CUT_FAILED",
        error_msg="FeatureCut3 returned null on overlapping geometry",
        part_family="followup_feature_v0",
    )
    assert rec.error_class == "CUT_FAILED"
    assert "hole_wizard" in rec.op_types
    assert rec.schema_version == SCHEMA_VERSION
    assert rec.fingerprint  # non-empty hash
    assert rec.occurrence_count == 1

    # The atomic-rewrite tempfile must not be left behind.
    assert not fm._MEMORY_PATH.with_suffix(".jsonl.tmp").exists()

    with fm._MEMORY_PATH.open(encoding="utf-8") as f:
        line = f.readline()
        data = json.loads(line)
    assert data["error_class"] == "CUT_FAILED"
    assert data["fingerprint"] == rec.fingerprint
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
    hits = relevant_failures("export to PDF", k=3, min_similarity=0.25)
    assert hits == []


# ── PII / secret scrubbing ────────────────────────────────────────────────────

def test_record_scrubs_windows_paths():
    rec = record_failure(
        prompt=r"open C:\Users\theof\secret\design.sldprt and fillet edges",
        op_types=["fillet"],
        error_class="X",
        error_msg=r"failed at C:\Users\theof\AppData\Local\app.log",
    )
    assert "C:\\Users\\theof" not in rec.prompt
    assert "C:\\Users\\theof" not in rec.error_msg
    assert "[PATH]" in rec.prompt
    assert "[PATH]" in rec.error_msg


def test_record_scrubs_emails_and_keys():
    rec = record_failure(
        prompt="send to design@acme.com with key sk-abcdef0123456789ABCDEF0123",
        op_types=[],
        error_class="X",
        error_msg="contact admin@acme.com (key AIzaSyD0123456789ABCDEF0123456789)",
    )
    assert "design@acme.com" not in rec.prompt
    assert "[EMAIL]" in rec.prompt
    assert "[SECRET]" in rec.prompt
    assert "[EMAIL]" in rec.error_msg
    assert "[SECRET]" in rec.error_msg


# ── Deduplication ─────────────────────────────────────────────────────────────

def test_same_failure_within_window_bumps_count_not_duplicate():
    a = record_failure(
        prompt="add four M6 counterbore holes at the corners",
        op_types=["hole_wizard", "rebuild"],
        error_class="CUT_FAILED",
        error_msg="overlap",
    )
    b = record_failure(
        prompt="add four M6 counterbore holes at the corners",
        op_types=["hole_wizard", "rebuild"],
        error_class="CUT_FAILED",
        error_msg="overlap (second time)",
    )
    # We get back the *same* record (in-memory), now with count=2.
    assert b.fingerprint == a.fingerprint
    assert b.occurrence_count == 2

    # Disk should contain exactly one line, not two.
    with fm._MEMORY_PATH.open(encoding="utf-8") as f:
        lines = [l for l in f if l.strip()]
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["occurrence_count"] == 2


def test_different_failures_do_not_dedup():
    record_failure("add holes", ["hole_wizard"], "CUT_FAILED", "x")
    record_failure("add fillet", ["fillet"],     "FILLET_FAILED", "y")
    with fm._MEMORY_PATH.open(encoding="utf-8") as f:
        lines = [l for l in f if l.strip()]
    assert len(lines) == 2


# ── Bounded growth ────────────────────────────────────────────────────────────

def test_max_records_evicts_oldest(monkeypatch):
    monkeypatch.setattr(fm, "MAX_RECORDS", 3)
    for i in range(10):
        # Distinct fingerprints so no dedup masks the eviction behaviour.
        record_failure(f"prompt number {i}", [f"op{i}"], f"ERR{i}", f"msg{i}")

    with fm._MEMORY_PATH.open(encoding="utf-8") as f:
        lines = [l for l in f if l.strip()]
    assert len(lines) == 3
    # Oldest should be evicted — only the last three remain.
    last_three_msgs = {json.loads(l)["error_msg"] for l in lines}
    assert last_three_msgs == {"msg7", "msg8", "msg9"}


# ── Corruption recovery ───────────────────────────────────────────────────────

def test_load_skips_corrupt_lines(tmp_path):
    record_failure("good prompt one", ["op"], "X", "y")
    # Manually corrupt the file by appending garbage.
    with fm._MEMORY_PATH.open("a", encoding="utf-8") as f:
        f.write("this is not json at all\n")
        f.write("{invalid json: indeed\n")
    _reset_cache_for_tests()

    # Adding a new record should succeed and we should keep the good one.
    record_failure("good prompt two", ["op2"], "Y", "y2")
    stats = memory_stats()
    assert stats["record_count"] == 2


# ── Summarisation + purge + stats ─────────────────────────────────────────────

def test_summarize_for_prompt_renders_compact_block():
    rec = FailureRecord.new(
        prompt="shell the box",
        op_types=["shell", "rebuild"],
        error_class="SHELL_FAILED",
        error_msg="wall too thin for steel",
    )
    block = summarize_for_prompt([rec])
    assert "PAST FAILURES" in block
    assert "shell" in block
    assert "SHELL_FAILED" in block


def test_summarize_for_prompt_returns_empty_when_no_failures():
    assert summarize_for_prompt([]) == ""


def test_purge_memory_resets_disk_and_cache():
    record_failure("p1", ["a"], "X", "y")
    record_failure("p2", ["b"], "Z", "y")
    removed = purge_memory()
    assert removed == 2
    assert not fm._MEMORY_PATH.exists()
    assert memory_stats()["record_count"] == 0


def test_memory_stats_reports_top_errors():
    record_failure("p1", ["a"], "CUT_FAILED", "y")
    record_failure("p2", ["b"], "FILLET_FAILED", "y")
    record_failure("p3", ["c"], "CUT_FAILED", "y")
    stats = memory_stats()
    assert stats["record_count"] == 3
    top = {e["class"]: e["count"] for e in stats["top_errors"]}
    assert top["CUT_FAILED"] == 2
    assert top["FILLET_FAILED"] == 1


# ── Token hygiene ─────────────────────────────────────────────────────────────

def test_tokens_drop_stopwords_and_short_words():
    rec = FailureRecord.new(
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


def test_record_caps_op_types_count():
    too_many = [f"op{i}" for i in range(100)]
    rec = record_failure("p", too_many, "X", "y")
    assert len(rec.op_types) <= 32


# ── Cross-process / restart simulation ────────────────────────────────────────

def test_records_survive_module_reload(monkeypatch):
    record_failure("prompt to survive restart", ["op"], "X", "y")
    # Simulate process restart by clearing the in-memory cache.
    _reset_cache_for_tests()
    hits = relevant_failures("prompt to survive restart")
    assert len(hits) == 1
    assert "survive" in hits[0].prompt
