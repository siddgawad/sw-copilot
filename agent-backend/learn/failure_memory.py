"""
Failure memory — record every executor failure and surface relevant past
failures to the planner so it does not repeat the same mistake.

Storage:  agent-backend/memory/failures.jsonl (append-only, one record per line)
Retrieval: keyword + intent-token overlap (no embedding cost on the hot path).

This is deliberately a *minimum-viable* memory. It is faster, more transparent,
and easier to audit than a vector store for the volume we expect (hundreds of
records over the lifetime of a single user's install).
"""
from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

# ── Storage location ──────────────────────────────────────────────────────────

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_MEMORY_DIR = _BACKEND_DIR / "memory"
_MEMORY_PATH = _MEMORY_DIR / "failures.jsonl"

_LOCK = threading.Lock()

# ── Tokenisation (cheap keyword overlap) ──────────────────────────────────────

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset({
    "the", "a", "an", "with", "and", "or", "on", "in", "of", "to", "for",
    "add", "make", "create", "build", "set", "is", "are", "this", "that",
    "by", "at", "from",
})


def _tokens(text: str) -> list[str]:
    if not text:
        return []
    return [t for t in _TOKEN_PATTERN.findall(text.lower()) if t not in _STOPWORDS and len(t) > 1]


def _token_set(text: str) -> set[str]:
    return set(_tokens(text))


# ── Records ───────────────────────────────────────────────────────────────────

@dataclass
class FailureRecord:
    """One failed execution. Append-only — never edited after write."""

    timestamp:   float
    prompt:      str            # what the user typed
    op_types:    list[str]      # ordered list of op types in the failing graph
    error_class: str            # error_type from C# executor or "VALIDATION_FAILED"
    error_msg:   str            # human-readable error message
    part_family: str            # "box_v0", "followup_feature_v0", "" for LLM-generated
    lesson:      str = ""       # short generalisation (filled by summarize_for_prompt)
    tokens:      list[str] = field(default_factory=list)

    @classmethod
    def from_failure(
        cls,
        prompt: str,
        op_types: Iterable[str],
        error_class: str,
        error_msg: str,
        part_family: str = "",
    ) -> "FailureRecord":
        op_list = list(op_types)
        return cls(
            timestamp   = time.time(),
            prompt      = (prompt or "").strip()[:512],
            op_types    = op_list,
            error_class = (error_class or "UNKNOWN").upper()[:64],
            error_msg   = (error_msg or "").strip()[:512],
            part_family = (part_family or "").strip()[:64],
            tokens      = _tokens(prompt or ""),
        )

    def to_dict(self) -> dict:
        return asdict(self)


# ── Persistence ───────────────────────────────────────────────────────────────

def _ensure_memory_dir() -> None:
    _MEMORY_DIR.mkdir(parents=True, exist_ok=True)


def record_failure(
    prompt: str,
    op_types: Iterable[str],
    error_class: str,
    error_msg: str,
    part_family: str = "",
) -> FailureRecord:
    """Append a failure to disk and return the record. Thread-safe."""
    record = FailureRecord.from_failure(prompt, op_types, error_class, error_msg, part_family)

    with _LOCK:
        _ensure_memory_dir()
        with _MEMORY_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")

    return record


def _load_all() -> list[FailureRecord]:
    if not _MEMORY_PATH.exists():
        return []

    records: list[FailureRecord] = []
    with _MEMORY_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                records.append(FailureRecord(**data))
            except (json.JSONDecodeError, TypeError):
                # Corrupt or schema-drifted line — skip silently.
                continue
    return records


def purge_memory() -> int:
    """Remove the failures file. Returns count of records removed."""
    with _LOCK:
        if not _MEMORY_PATH.exists():
            return 0
        count = sum(1 for _ in _MEMORY_PATH.open("r", encoding="utf-8") if _.strip())
        _MEMORY_PATH.unlink()
    return count


# ── Retrieval ─────────────────────────────────────────────────────────────────

def _similarity(query_tokens: set[str], record_tokens: set[str]) -> float:
    """Jaccard similarity (intersection over union)."""
    if not query_tokens or not record_tokens:
        return 0.0
    inter = len(query_tokens & record_tokens)
    union = len(query_tokens | record_tokens)
    return inter / union if union else 0.0


def relevant_failures(prompt: str, k: int = 3, min_similarity: float = 0.25) -> list[FailureRecord]:
    """
    Return up to k past failures most relevant to the current prompt.
    Filtered by minimum Jaccard similarity over keyword tokens.
    """
    if not prompt:
        return []

    query_tokens = set(_tokens(prompt))
    if not query_tokens:
        return []

    scored: list[tuple[float, FailureRecord]] = []
    for record in _load_all():
        score = _similarity(query_tokens, set(record.tokens))
        if score >= min_similarity:
            scored.append((score, record))

    scored.sort(key=lambda pair: (pair[0], pair[1].timestamp), reverse=True)
    return [rec for _, rec in scored[:k]]


# ── Prompt injection helpers ──────────────────────────────────────────────────

def summarize_for_prompt(failures: list[FailureRecord], max_chars: int = 800) -> str:
    """
    Render relevant failures as a compact 'lessons' block for the LLM system
    prompt. Empty string if no failures — caller should not inject anything.
    """
    if not failures:
        return ""

    lines = ["PAST FAILURES (similar prompts that previously broke — do NOT repeat these patterns):"]
    for rec in failures:
        chain = " -> ".join(rec.op_types[:6]) if rec.op_types else "(no ops)"
        family = f" [{rec.part_family}]" if rec.part_family else ""
        snippet = rec.error_msg.replace("\n", " ")[:160]
        lines.append(
            f"- Prompt: \"{rec.prompt[:120]}\"{family}"
            f"\n  Pattern: {chain}"
            f"\n  Failed with {rec.error_class}: {snippet}"
        )

    summary = "\n".join(lines)
    if len(summary) > max_chars:
        summary = summary[: max_chars - 20] + "\n... [truncated]"
    return summary
