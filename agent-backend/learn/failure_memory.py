"""
Failure memory — production-grade self-improvement subsystem.

Records every executor failure and surfaces relevant past failures to the
planner so it does not repeat the same mistake. Survives across sessions.

Design goals (in order of priority):
  1. Safety — never corrupt the store, never crash callers on bad data,
     never log secrets/PII to disk.
  2. Bounded growth — disk and memory usage stay constant after the cap.
  3. Fast retrieval — O(N) over a small N kept entirely in memory.
  4. Crash-safe writes — atomic temp+rename so a power loss can never
     produce a half-written file.
  5. Auditability — append-only model with deduplication via occurrence
     counter (we mutate counts, never edit historical content).

Storage:
  agent-backend/memory/failures.jsonl  — canonical store (atomic rewrites)
  agent-backend/memory/.failures.lock  — best-effort cross-process lock

Retrieval:
  Jaccard similarity over keyword tokens. No embedding cost on the hot path.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Optional

_LOG = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

SCHEMA_VERSION       = 1
MAX_RECORDS          = 1000   # disk + memory cap; evict oldest beyond this
DEDUP_WINDOW_SECONDS = 3600   # same failure pattern within 1h bumps the count
MAX_PROMPT_CHARS     = 512
MAX_ERROR_CHARS      = 512
MAX_PART_FAMILY      = 64
MAX_OP_TYPES_PER_REC = 32

# ── Storage location ──────────────────────────────────────────────────────────

_BACKEND_DIR  = Path(__file__).resolve().parent.parent
_MEMORY_DIR   = _BACKEND_DIR / "memory"
_MEMORY_PATH  = _MEMORY_DIR / "failures.jsonl"

# In-memory cache and lock. The cache is the source of truth at runtime; disk
# is the source of truth at startup. We rewrite disk atomically on every change.
_LOCK: threading.Lock           = threading.Lock()
_CACHE: Optional[list["FailureRecord"]] = None  # lazily loaded


# ── PII / secret scrubbing ────────────────────────────────────────────────────

# Defensive patterns. We are running on the user's local machine and the worst
# case is a future remote-sync feature picking up PII the user didn't intend
# to share. Better to scrub now than retrofit later.
_PATH_PATTERNS = [
    re.compile(r"[A-Za-z]:\\[^\s,;'\"<>|]+"),     # C:\Users\... — Windows paths
    re.compile(r"/(?:Users|home|root)/[^\s,;'\"<>|]+"),  # /Users/... /home/...
]
_EMAIL_PATTERN  = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Common API key prefixes we never want in the failure log.
_SECRET_PATTERN = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{20,}|gsk_[A-Za-z0-9_-]{20,}|AIza[A-Za-z0-9_-]{20,}|nvapi-[A-Za-z0-9_-]{20,})"
)
_CONTROL_CHARS  = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _scrub(text: str) -> str:
    if not text:
        return ""
    for pat in _PATH_PATTERNS:
        text = pat.sub("[PATH]", text)
    text = _EMAIL_PATTERN.sub("[EMAIL]", text)
    text = _SECRET_PATTERN.sub("[SECRET]", text)
    text = _CONTROL_CHARS.sub(" ", text)
    return text.strip()


# ── Tokenisation (cheap keyword overlap) ──────────────────────────────────────

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset({
    "the", "a", "an", "with", "and", "or", "on", "in", "of", "to", "for",
    "add", "make", "create", "build", "set", "is", "are", "this", "that",
    "by", "at", "from", "it", "be", "as",
})


def _tokens(text: str) -> list[str]:
    if not text:
        return []
    return [
        t for t in _TOKEN_PATTERN.findall(text.lower())
        if t not in _STOPWORDS and len(t) > 1
    ]


# ── Records ───────────────────────────────────────────────────────────────────

def _prompt_fingerprint(prompt: str, error_class: str, op_types: list[str]) -> str:
    """Short stable hash over the dedup-relevant fields."""
    tokens = " ".join(sorted(set(_tokens(prompt))))
    chain  = ",".join(op_types[:MAX_OP_TYPES_PER_REC])
    digest = hashlib.sha256(f"{tokens}|{error_class}|{chain}".encode("utf-8")).hexdigest()
    return digest[:16]


@dataclass
class FailureRecord:
    """One distinct failure pattern. Occurrence count tracks repeats."""

    timestamp:        float          # last-seen time (UTC epoch seconds)
    first_seen:       float
    fingerprint:      str
    prompt:           str
    op_types:         list[str]
    error_class:      str
    error_msg:        str
    part_family:      str
    occurrence_count: int            = 1
    schema_version:   int            = SCHEMA_VERSION
    tokens:           list[str]      = field(default_factory=list)

    @classmethod
    def new(
        cls,
        prompt: str,
        op_types: Iterable[str],
        error_class: str,
        error_msg: str,
        part_family: str = "",
    ) -> "FailureRecord":
        now = time.time()
        clean_prompt = _scrub(prompt)[:MAX_PROMPT_CHARS]
        clean_error  = _scrub(error_msg)[:MAX_ERROR_CHARS]
        clean_class  = (error_class or "UNKNOWN").upper().strip()[:64]
        clean_family = _scrub(part_family)[:MAX_PART_FAMILY]
        op_list = [
            str(t).strip()[:32] for t in (op_types or [])
            if t and isinstance(t, str)
        ][:MAX_OP_TYPES_PER_REC]
        return cls(
            timestamp        = now,
            first_seen       = now,
            fingerprint      = _prompt_fingerprint(clean_prompt, clean_class, op_list),
            prompt           = clean_prompt,
            op_types         = op_list,
            error_class      = clean_class,
            error_msg        = clean_error,
            part_family      = clean_family,
            occurrence_count = 1,
            schema_version   = SCHEMA_VERSION,
            tokens           = _tokens(clean_prompt),
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "FailureRecord":
        """Build a record from disk. Tolerates missing/extra fields."""
        # Defaults make us forward-compatible with future v2 records that
        # were partially deserialized; if the schema bumps, we'll add migration.
        return cls(
            timestamp        = float(data.get("timestamp", time.time())),
            first_seen       = float(data.get("first_seen", data.get("timestamp", time.time()))),
            fingerprint      = str(data.get("fingerprint", "")),
            prompt           = str(data.get("prompt", ""))[:MAX_PROMPT_CHARS],
            op_types         = list(data.get("op_types", []))[:MAX_OP_TYPES_PER_REC],
            error_class      = str(data.get("error_class", "UNKNOWN"))[:64],
            error_msg        = str(data.get("error_msg", ""))[:MAX_ERROR_CHARS],
            part_family      = str(data.get("part_family", ""))[:MAX_PART_FAMILY],
            occurrence_count = int(data.get("occurrence_count", 1)),
            schema_version   = int(data.get("schema_version", 0)),
            tokens           = list(data.get("tokens", [])),
        )


# ── Persistence (atomic + bounded) ────────────────────────────────────────────

def _ensure_memory_dir() -> None:
    _MEMORY_DIR.mkdir(parents=True, exist_ok=True)


def _atomic_rewrite(records: list[FailureRecord]) -> None:
    """Write the whole store atomically: temp file + fsync + rename.

    The OS guarantees that after rename completes, either the new file is in
    place (success) or the old file is still there (failure). There is no
    in-between state where the file is partially written.
    """
    _ensure_memory_dir()
    tmp_path = _MEMORY_PATH.with_suffix(".jsonl.tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")
            f.flush()
            try:
                os.fsync(f.fileno())
            except (OSError, AttributeError):
                # fsync unavailable on some filesystems (network shares, etc.)
                pass
        # Replace is atomic on Windows and POSIX.
        os.replace(str(tmp_path), str(_MEMORY_PATH))
    except Exception as exc:
        _LOG.warning("Failed to atomic-rewrite failure memory: %s", exc)
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def _load_disk_records() -> list[FailureRecord]:
    """Load every well-formed record from disk. Corrupt lines are skipped."""
    if not _MEMORY_PATH.exists():
        return []

    records: list[FailureRecord] = []
    corrupt = 0
    try:
        with _MEMORY_PATH.open("r", encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        records.append(FailureRecord.from_dict(data))
                    else:
                        corrupt += 1
                except (json.JSONDecodeError, TypeError, ValueError):
                    corrupt += 1
                    continue
    except OSError as exc:
        _LOG.warning("Failed to read failure memory: %s", exc)
        return []

    if corrupt:
        _LOG.info("Skipped %d corrupt failure-memory lines", corrupt)

    # Sort by timestamp ascending so eviction = drop head.
    records.sort(key=lambda r: r.timestamp)
    return records


def _ensure_cache() -> list[FailureRecord]:
    """Lazily load the cache from disk. Called under _LOCK."""
    global _CACHE
    if _CACHE is None:
        _CACHE = _load_disk_records()
        if len(_CACHE) > MAX_RECORDS:
            # File grew larger than the new cap — truncate on next write.
            _CACHE = _CACHE[-MAX_RECORDS:]
    return _CACHE


def _find_dedup_target(
    cache: list[FailureRecord],
    fingerprint: str,
    now: float,
) -> FailureRecord | None:
    """If a record with the same fingerprint exists within the dedup window,
    return it so the caller can mutate its count instead of appending."""
    for rec in reversed(cache):  # recent first
        if rec.fingerprint != fingerprint:
            continue
        if now - rec.timestamp <= DEDUP_WINDOW_SECONDS:
            return rec
        return None
    return None


# ── Public API ────────────────────────────────────────────────────────────────

def record_failure(
    prompt: str,
    op_types: Iterable[str],
    error_class: str,
    error_msg: str,
    part_family: str = "",
) -> FailureRecord:
    """Append (or dedup-merge) a failure record. Thread-safe, crash-safe.

    If the exact failure pattern was seen within DEDUP_WINDOW_SECONDS, the
    existing record's occurrence_count is incremented and timestamp updated,
    so the JSONL store never accumulates duplicate spam.
    """
    record = FailureRecord.new(prompt, op_types, error_class, error_msg, part_family)

    with _LOCK:
        cache = _ensure_cache()
        existing = _find_dedup_target(cache, record.fingerprint, record.timestamp)
        if existing is not None:
            existing.occurrence_count += 1
            existing.timestamp = record.timestamp
            # Refresh error message in case wording drifted slightly.
            existing.error_msg = record.error_msg
        else:
            cache.append(record)
            # Evict oldest beyond the cap.
            while len(cache) > MAX_RECORDS:
                cache.pop(0)

        _atomic_rewrite(cache)

    return existing if existing is not None else record


def _similarity(query_tokens: set[str], record_tokens: set[str]) -> float:
    """Jaccard similarity (intersection over union)."""
    if not query_tokens or not record_tokens:
        return 0.0
    inter = len(query_tokens & record_tokens)
    union = len(query_tokens | record_tokens)
    return inter / union if union else 0.0


def relevant_failures(
    prompt: str,
    k: int = 3,
    min_similarity: float = 0.25,
) -> list[FailureRecord]:
    """Top-k past failures most relevant to `prompt`. Empty if cache is empty
    or no record exceeds min_similarity."""
    if not prompt:
        return []

    query_tokens = set(_tokens(prompt))
    if not query_tokens:
        return []

    with _LOCK:
        cache_snapshot = list(_ensure_cache())  # cheap copy of references

    scored: list[tuple[float, FailureRecord]] = []
    for record in cache_snapshot:
        score = _similarity(query_tokens, set(record.tokens))
        if score >= min_similarity:
            scored.append((score, record))

    # Higher similarity > more recent > higher occurrence count.
    scored.sort(
        key=lambda pair: (pair[0], pair[1].timestamp, pair[1].occurrence_count),
        reverse=True,
    )
    return [rec for _, rec in scored[:k]]


def summarize_for_prompt(failures: list[FailureRecord], max_chars: int = 800) -> str:
    """Render relevant failures as a compact 'lessons' block for the LLM
    system prompt. Empty string if no failures."""
    if not failures:
        return ""

    lines = [
        "PAST FAILURES (similar prompts that previously broke — do NOT repeat these patterns):"
    ]
    for rec in failures:
        chain = " -> ".join(rec.op_types[:6]) if rec.op_types else "(no ops)"
        family = f" [{rec.part_family}]" if rec.part_family else ""
        repeats = f" (seen {rec.occurrence_count}x)" if rec.occurrence_count > 1 else ""
        snippet = rec.error_msg.replace("\n", " ")[:160]
        lines.append(
            f"- Prompt: \"{rec.prompt[:120]}\"{family}{repeats}"
            f"\n  Pattern: {chain}"
            f"\n  Failed with {rec.error_class}: {snippet}"
        )

    summary = "\n".join(lines)
    if len(summary) > max_chars:
        summary = summary[: max_chars - 20] + "\n... [truncated]"
    return summary


def purge_memory() -> int:
    """Reset the memory store. Returns number of records removed."""
    global _CACHE
    with _LOCK:
        count = len(_CACHE) if _CACHE is not None else 0
        _CACHE = []
        if _MEMORY_PATH.exists():
            try:
                _MEMORY_PATH.unlink()
            except OSError as exc:
                _LOG.warning("Failed to delete failure memory: %s", exc)
    return count


def memory_stats() -> dict:
    """Health check: how big is the store and what does it know about."""
    with _LOCK:
        cache = _ensure_cache()
        records = list(cache)

    if not records:
        return {
            "record_count":  0,
            "max_records":   MAX_RECORDS,
            "schema_version": SCHEMA_VERSION,
            "oldest":         None,
            "newest":         None,
            "top_errors":     [],
        }

    # Tally error classes.
    error_counts: dict[str, int] = {}
    for rec in records:
        error_counts[rec.error_class] = error_counts.get(rec.error_class, 0) + rec.occurrence_count
    top_errors = sorted(error_counts.items(), key=lambda kv: kv[1], reverse=True)[:5]

    return {
        "record_count":   len(records),
        "max_records":    MAX_RECORDS,
        "schema_version": SCHEMA_VERSION,
        "oldest":         records[0].timestamp,
        "newest":         records[-1].timestamp,
        "top_errors":     [{"class": cls, "count": ct} for cls, ct in top_errors],
    }


# ── Test/debug helpers ────────────────────────────────────────────────────────

def _reset_cache_for_tests() -> None:
    """Reset the in-memory cache. Test-only — called from conftest fixtures."""
    global _CACHE
    with _LOCK:
        _CACHE = None
