"""Self-improvement subsystem — production-grade failure memory + retrieval."""
from .failure_memory import (
    DEDUP_WINDOW_SECONDS,
    MAX_RECORDS,
    SCHEMA_VERSION,
    FailureRecord,
    memory_stats,
    purge_memory,
    record_failure,
    relevant_failures,
    summarize_for_prompt,
    _reset_cache_for_tests,
)

__all__ = [
    "DEDUP_WINDOW_SECONDS",
    "MAX_RECORDS",
    "SCHEMA_VERSION",
    "FailureRecord",
    "memory_stats",
    "purge_memory",
    "record_failure",
    "relevant_failures",
    "summarize_for_prompt",
    "_reset_cache_for_tests",
]
