"""Self-improvement subsystem — failure memory and lesson retrieval."""
from .failure_memory import (
    FailureRecord,
    record_failure,
    relevant_failures,
    summarize_for_prompt,
    purge_memory,
)

__all__ = [
    "FailureRecord",
    "record_failure",
    "relevant_failures",
    "summarize_for_prompt",
    "purge_memory",
]
