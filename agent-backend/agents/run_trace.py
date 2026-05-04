"""
Run trace archiver — saves every generate/validate call to disk.

Every interaction produces a timestamped folder under runs/:

    runs/
      20260504_143022_123456_spur_gear_20T_m2/
        prompt.txt
        source.txt          ("pattern" | "base_plate_v0" | "llm")
        operation_graph.json
        executor_result.json   (written by /validate)
        part_report.json       (written by /validate)
        validation_report.json (written by /validate)

These are clean, structured training traces.  Not internet text.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from models.schemas import (
    ExecutorRunResult,
    OperationGraph,
    PartReport,
    ValidationReport,
)

_RUNS_DIR = Path("runs")
_SLUG_RE  = re.compile(r"[^a-z0-9]+")


def _slug(text: str | None, max_len: int = 24) -> str:
    if not text:
        return "part"
    return _SLUG_RE.sub("_", text.lower().strip())[:max_len].strip("_")


def make_trace_id(part_name: str | None = None) -> str:
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    name = _slug(part_name)
    return f"{ts}_{name}"


def _run_dir(trace_id: str) -> Path:
    return _RUNS_DIR / trace_id


def save_generate_trace(
    trace_id: str,
    prompt: str,
    graph: OperationGraph,
    source: str = "llm",          # "llm" | "pattern" | "base_plate_v0"
) -> Path:
    """
    Write prompt + operation_graph at /generate time.
    Returns the run directory so the caller can log it.
    """
    d = _run_dir(trace_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "prompt.txt"         ).write_text(prompt,           encoding="utf-8")
    (d / "source.txt"         ).write_text(source,           encoding="utf-8")
    (d / "operation_graph.json").write_text(
        graph.model_dump_json(indent=2), encoding="utf-8"
    )
    return d


def save_validation_trace(
    trace_id: str,
    executor_result: Optional[ExecutorRunResult],
    part_report: PartReport,
    validation_report: ValidationReport,
) -> None:
    """
    Append executor + validation artifacts to an existing trace folder.
    Creates the folder if it doesn't exist (validate-only call with no prior generate).
    """
    d = _run_dir(trace_id)
    d.mkdir(parents=True, exist_ok=True)
    if executor_result is not None:
        (d / "executor_result.json").write_text(
            executor_result.model_dump_json(indent=2), encoding="utf-8"
        )
    (d / "part_report.json"       ).write_text(
        part_report.model_dump_json(indent=2),       encoding="utf-8"
    )
    (d / "validation_report.json" ).write_text(
        validation_report.model_dump_json(indent=2), encoding="utf-8"
    )
