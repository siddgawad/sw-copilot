"""Build123dBackend — the orchestrator.

Walks an OperationGraph and dispatches each op to its registered handler.
Catches handler exceptions and records them on the context as errors so
one bad op never aborts the whole graph.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .context import ExecutionContext
from .op_handlers import HANDLERS

if TYPE_CHECKING:
    from models.schemas import OperationGraph
    from .result import Build123dResult


_log = logging.getLogger("sw_copilot.validation")


class Build123dBackend:
    """Run an OperationGraph headlessly in build123d.

    Usage
    -----
        result = Build123dBackend().execute(graph)
        if not result.success:
            print(result.errors)
        else:
            print(result.bounding_box_mm)
    """

    def __init__(self) -> None:
        self._handlers = HANDLERS

    def execute(self, graph: "OperationGraph") -> "Build123dResult":
        ctx = ExecutionContext()
        for op in graph.operations:
            handler = self._handlers.get(op.type)
            if handler is None:
                ctx.add_error(
                    op.id,
                    "UnsupportedOp",
                    f"No build123d handler for op type {op.type!r} "
                    f"(register it in validation/op_handlers/__init__.py).",
                )
                continue
            try:
                handler.execute(op, ctx)
            except Exception as exc:  # noqa: BLE001 — we record and continue
                _log.exception("handler %s failed for op %s", op.type, op.id)
                ctx.add_error(op.id, type(exc).__name__, str(exc))
                # On a hard failure (e.g. no part to cut), break — further
                # ops will compound the error in confusing ways.
                if isinstance(exc, (RuntimeError, ValueError, KeyError)):
                    break
        return ctx.to_result()
