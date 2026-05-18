"""Headless OperationGraph validation via build123d.

Public API:
    Build123dBackend  — run an OperationGraph headlessly
    Build123dResult   — geometric report (bbox, body count, etc.)

The backend is deliberately a thin orchestrator: each op type has a handler
in op_handlers/, and the registry dispatches by op.type. Handlers are
self-contained and can be implemented one at a time without touching the
rest of the codebase. See docs/VALIDATION_HARNESS_DESIGN.md.
"""
from .backend import Build123dBackend
from .result import Build123dResult, SketchInfo

__all__ = ["Build123dBackend", "Build123dResult", "SketchInfo"]
