"""Op handler ABC. Every concrete handler in this package extends OpHandler.

Contract (read this before implementing a handler):

1. A handler is a stateless callable. All graph state lives on
   `ExecutionContext`. Do not store state on `self`.

2. `execute(op, ctx)` must mutate ctx in place. Never return geometry.

3. Geometric errors must raise Python exceptions. The Build123dBackend
   wraps every handler call in a try/except and records the error onto
   ctx — do NOT call `ctx.add_error` yourself for the normal failure path.
   `ctx.add_error` is for *partial* failures inside an otherwise-successful
   handler (e.g. one of N positions in hole_wizard is out of bounds).

4. Handlers must not call into SolidWorks COM, file I/O, or network.
   Pure build123d + ISO standards lookups only. CI runs on Linux.

5. The op_type attribute is the dispatch key used by the registry. Set it
   on the class (class-level attribute), not in __init__.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..context import ExecutionContext


class OpHandler(ABC):
    """Base class for all op handlers."""

    #: The op.type string this handler claims. Used by the registry.
    op_type: str = ""

    @abstractmethod
    def execute(self, op: Any, ctx: ExecutionContext) -> None:
        """Apply the operation to the context.

        Parameters
        ----------
        op
            The op Pydantic instance (CreatePartOp, ExtrudeBossOp, etc.).
            The discriminated union is in models.schemas as `Operation`.
            Pydantic has already validated its types and required fields
            — don't re-validate.
        ctx
            The mutable execution context. Read prior state, write new
            state, raise on geometric error.
        """
        raise NotImplementedError
