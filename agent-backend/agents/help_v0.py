"""Deterministic handler for capability/help/greeting prompts. No LLM required."""
import re
from typing import Optional
from models.schemas import OperationGraph

_HELP_PATTERN = re.compile(
    r"^\s*(hi|hello|hey|what can you do|what do you do|help|capabilities|"
    r"how (do you|does this) work|what (are|is) (your|the) (capabilities|features|operations)|"
    r"what can i (do|ask|say)|show me (what|how)|getting started|start)\b",
    re.IGNORECASE,
)

_HELP_MESSAGE = (
    "I'm SW Copilot — I translate natural language into SolidWorks actions.\n\n"
    "GEOMETRY CREATION:\n"
    "  • \"create a 50mm wide 30mm deep 20mm tall box\"\n"
    "  • \"create a 40mm diameter shaft 100mm long\"\n"
    "  • \"add four M6 counterbore holes at the corners\"\n"
    "  • \"add a 2mm fillet on all edges\"\n"
    "  • \"add 6 M5 holes on a 60mm bolt circle\"\n\n"
    "WORKFLOW AUTOMATION:\n"
    "  • \"set revision to C, drawn by [name], date today\"\n"
    "  • \"export this as PDF\"\n"
    "  • \"export as DXF with revision in the filename\"\n"
    "  • \"check this drawing for problems\" (drawing documents only)\n\n"
    "EDITING:\n"
    "  • \"add a chamfer on the top edges\"\n"
    "  • \"delete everything\" or \"delete the last feature\"\n"
    "  • \"mirror across the right plane\"\n\n"
    "ISO STANDARDS:\n"
    "  Fastener sizes (M3-M30) are looked up from ISO 273/4762 tables automatically — "
    "I don't guess dimensions.\n\n"
    "Open a part or drawing and type what you want to build or do."
)


def match(prompt: str) -> bool:
    return bool(_HELP_PATTERN.match(prompt.strip()))


def build_graph() -> OperationGraph:
    return OperationGraph(
        schema_version="0.2",
        part_name=None,
        reasoning="Deterministic help response — no LLM needed.",
        operations=[{"id": "help1", "type": "noop", "message": _HELP_MESSAGE}],
    )


def try_generate(prompt: str) -> Optional[OperationGraph]:
    if not match(prompt):
        return None
    return build_graph()
