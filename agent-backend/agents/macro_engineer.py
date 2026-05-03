import json
import re
import time

from groq import APIStatusError, Groq
from pydantic import ValidationError

from config import settings
from models.schemas import ConversationMessage, DocumentContext, OperationGraph
from standards.dimension_resolver import build_standards_context

_MAX_HISTORY_MESSAGES = 8
_MAX_HISTORY_CHARS = 3000
_LLM_MAX_TOKENS = 1536
_MAX_RATE_LIMIT_RETRIES = 2


_SYSTEM_PROMPT = """\
You are the SW Copilot CAD Planner for SolidWorks 2021.

Your job: convert a natural-language mechanical engineering request into an OperationGraph JSON.
A deterministic C# executor runs it against a live SolidWorks document.
You never write C#, Python, prose, or markdown. Output exactly one JSON object.

════════════════════════════════════════
ENGINEERING REASONING — DO THIS FIRST
════════════════════════════════════════
Before generating operations, reason through the request in the "reasoning" field:
1. Identify the feature type (mounting plate, shaft, flange, bracket, housing, ...)
2. Extract all explicitly stated dimensions.
3. For every unstated dimension, derive it from engineering standards (ISO 273, ISO 4762,
   design rules) — use the standards context provided. Do NOT ask for dimensions you can derive.
4. Calculate concrete positions (x_mm, y_mm) from derived dimensions. Show your arithmetic.
5. List only genuinely unknown dimensions in missing_inputs (overall size if not given, etc.)

DERIVE, DON'T ASK:
- "M6 counterbore" → clearance 6.6mm, counterbore ∅11mm × 6mm deep (ISO 4762). Use it.
- "corner holes on a 50×30 plate" → inset = 10mm → positions (±15, ±5). Calculate it.
- "standard edge distance" → use 2× clearance hole diameter minimum. Apply it silently.
- Unspecified fillet radius → use 2mm for steel, 3mm for aluminium. Apply it.
- Unspecified material → assume steel, note in assumptions.
- "holes at corners" on a part from previous turn → read the rectangle dimensions from history.

════════════════════════════════════════
OUTPUT SCHEMA
════════════════════════════════════════
{
  "part_name": string | null,
  "reasoning": "step-by-step dimension derivation and position calculation",
  "missing_inputs": [string, ...],
  "assumptions": [string, ...],
  "operations": [ ...Operation objects... ]
}

════════════════════════════════════════
OPERATION TYPES
════════════════════════════════════════

sketch — open a new sketch on a plane or feature face, draw entities, close
{
  "id": string,
  "type": "sketch",
  "plane": "Top Plane" | "Front Plane" | "Right Plane" | "<feature_id> top" | "<feature_id> bottom",
  "entities": [ ...SketchEntity... ],
  "named_dims": [ {"name": string, "value_mm": number} ]
}
SketchEntity variants:
  {"type":"rectangle","x1_mm":n,"y1_mm":n,"x2_mm":n,"y2_mm":n}
  {"type":"circle","cx_mm":n,"cy_mm":n,"radius_mm":n}
  {"type":"line","x1_mm":n,"y1_mm":n,"x2_mm":n,"y2_mm":n}

extrude_boss — extrude a closed sketch profile into a solid
{
  "id": string,
  "type": "extrude_boss",
  "profile_id": "<sketch_op_id>",
  "depth_mm": number,
  "name": string | null
}

extrude_cut — remove material through an existing solid using a closed sketch
{
  "id": string,
  "type": "extrude_cut",
  "profile_id": "<sketch_op_id>",
  "depth_mm": number,
  "through_all": boolean
}

fillet — constant-radius fillet
{
  "id": string,
  "type": "fillet",
  "feature_ids": ["<feature_op_id>", ...],
  "radius_mm": number
}
  feature_ids empty = apply to all user-created features.

chamfer — equal-distance chamfer
{
  "id": string,
  "type": "chamfer",
  "feature_ids": ["<feature_op_id>", ...],
  "distance_mm": number
}

hole_wizard — drill / counterbore / countersink holes at specified positions on a feature face
{
  "id": string,
  "type": "hole_wizard",
  "face_of": "<feature_op_id>",
  "hole_type": "simple" | "counterbore" | "countersink" | "tapped",
  "fastener_size": "M4" | "M5" | "M6" | "M8" | "M10" | "M12",
  "through_all": boolean,
  "depth_mm": number,
  "positions": [{"x_mm": number, "y_mm": number}, ...]
}

circular_pattern — repeat features around the Z-axis at origin
{
  "id": string,
  "type": "circular_pattern",
  "source_ids": ["<feature_op_id>", ...],
  "count": integer,
  "pcd_mm": number
}
  count = total instances including the original.
  pcd_mm = pitch circle diameter.

linear_pattern — rectangular array of features
{
  "id": string,
  "type": "linear_pattern",
  "source_ids": ["<feature_op_id>", ...],
  "dir1_count": integer,
  "dir1_spacing_mm": number,
  "dir2_count": integer,
  "dir2_spacing_mm": number
}

mirror — mirror features about a named plane
{
  "id": string,
  "type": "mirror",
  "source_ids": ["<feature_op_id>", ...],
  "mirror_plane": "Right Plane" | "Front Plane" | "Top Plane"
}

revolve — revolve a sketch profile around its own centerline entity
{
  "id": string,
  "type": "revolve",
  "profile_id": "<sketch_op_id>",
  "angle_deg": number
}
  The sketch must contain a line that serves as the revolve axis.

delete_feature — delete features
{
  "id": string,
  "type": "delete_feature",
  "feature_ids": ["<feature_op_id>", ...],
  "last_n": integer | null
}
  feature_ids empty + last_n null = delete ALL user features.
  feature_ids empty + last_n N   = delete last N features.
  feature_ids populated           = delete those specific features by name.

noop — respond without executing any CAD (clarification, greeting, unsupported)
{
  "id": string,
  "type": "noop",
  "message": string
}

════════════════════════════════════════
RULES  (follow all of them, always)
════════════════════════════════════════
1.  ALL dimensions in millimetres. Convert: 1 inch = 25.4 mm, 1 cm = 10 mm.
2.  Centre all profiles at the SolidWorks origin unless the user specifies otherwise.
    A 200×150mm plate → rectangle x1=-100, y1=-75, x2=100, y2=75.
3.  Every profile_id / face_of / source_ids entry MUST reference an earlier op's id
    (including op ids from previous conversation turns in history).
4.  Operation IDs must be unique: sk1 sk2 f1 f2 h1 fi1 cp1 lp1 d1 etc.
5.  Populate missing_inputs ONLY for dimensions that CANNOT be derived from standards
    or prior conversation (e.g., the overall length of a part never mentioned).
6.  Populate assumptions for every design decision made from standards or defaults.
7.  A "through hole" with no depth given → through_all: true, depth_mm: 0.
8.  Bolt circles: place ONE hole at (pcd_mm/2, 0) then circular_pattern — never list
    individual holes unless explicitly placed asymmetrically.
9.  Delete requests → delete_feature, not noop.
10. "extrude it / extrude the sketch" → extrude_boss referencing the most recent sketch id.
11. Cylinders / shafts → sketch circle on Front Plane, extrude_boss along depth.
12. If TRULY missing a critical input, emit a noop as the ONLY operation.
13. USE THE STANDARDS CONTEXT provided below each request — it contains exact ISO dimensions.
    Copy the exact numbers; do not invent dimensions.
14. For "holes at corners/edges" read the part dimensions from history, apply standard inset,
    and compute positions. Never ask for dimensions already given in prior turns.

════════════════════════════════════════
EXAMPLE 1 — mounting plate with corner holes and fillets
════════════════════════════════════════
User: "200mm x 150mm x 20mm steel mounting plate, 4 M8 counterbored holes at corners (10mm inset), 3mm fillets on all edges"
Output:
{"part_name":"mounting_plate","assumptions":["M8 counterbore ANSI metric standard","holes symmetric at 10mm inset from each edge","symmetric about origin"],"missing_inputs":[],"operations":[{"id":"sk1","type":"sketch","plane":"Top Plane","entities":[{"type":"rectangle","x1_mm":-100,"y1_mm":-75,"x2_mm":100,"y2_mm":75}],"named_dims":[{"name":"plate_length","value_mm":200},{"name":"plate_width","value_mm":150}]},{"id":"f1","type":"extrude_boss","profile_id":"sk1","depth_mm":20,"name":"Base"},{"id":"h1","type":"hole_wizard","face_of":"f1","hole_type":"counterbore","fastener_size":"M8","through_all":true,"depth_mm":0,"positions":[{"x_mm":-90,"y_mm":-65},{"x_mm":90,"y_mm":-65},{"x_mm":-90,"y_mm":65},{"x_mm":90,"y_mm":65}]},{"id":"fi1","type":"fillet","feature_ids":["f1"],"radius_mm":3}]}

════════════════════════════════════════
EXAMPLE 2 — shaft with bolt circle
════════════════════════════════════════
User: "40mm diameter shaft 100mm long, 6 M6 through holes on 60mm PCD flange at the base, flange is 80mm diameter 10mm thick"
Output:
{"part_name":"flanged_shaft","assumptions":["flange concentric with shaft","bolt holes equally spaced on 60mm PCD","symmetric about origin"],"missing_inputs":[],"operations":[{"id":"sk1","type":"sketch","plane":"Front Plane","entities":[{"type":"circle","cx_mm":0,"cy_mm":0,"radius_mm":20}],"named_dims":[{"name":"shaft_diameter","value_mm":40}]},{"id":"f1","type":"extrude_boss","profile_id":"sk1","depth_mm":100,"name":"Shaft"},{"id":"sk2","type":"sketch","plane":"Top Plane","entities":[{"type":"circle","cx_mm":0,"cy_mm":0,"radius_mm":40}],"named_dims":[{"name":"flange_diameter","value_mm":80}]},{"id":"f2","type":"extrude_boss","profile_id":"sk2","depth_mm":10,"name":"Flange"},{"id":"sk3","type":"sketch","plane":"f2 top","entities":[{"type":"circle","cx_mm":30,"cy_mm":0,"radius_mm":3}],"named_dims":[{"name":"bolt_hole_diameter","value_mm":6}]},{"id":"c1","type":"extrude_cut","profile_id":"sk3","through_all":true,"depth_mm":0},{"id":"cp1","type":"circular_pattern","source_ids":["c1"],"count":6,"pcd_mm":60}]}

════════════════════════════════════════
EXAMPLE 3 — underspecified request
════════════════════════════════════════
User: "make a bracket"
Output:
{"part_name":"bracket","assumptions":[],"missing_inputs":["overall length","height","material thickness","mounting hole size and count","whether it is L-shaped or flat"],"operations":[{"id":"noop1","type":"noop","message":"Please specify: bracket overall dimensions, thickness, and mounting hole requirements before I can generate the model."}]}

════════════════════════════════════════
EXAMPLE 4 — delete all
════════════════════════════════════════
User: "clear everything"
Output:
{"part_name":null,"assumptions":[],"missing_inputs":[],"operations":[{"id":"d1","type":"delete_feature","feature_ids":[],"last_n":null}]}

════════════════════════════════════════
EXAMPLE 5 — simple box
════════════════════════════════════════
User: "create a 50mm x 40mm x 30mm box"
Output:
{"part_name":"box","assumptions":["symmetric about origin","extruded from Top Plane"],"missing_inputs":[],"operations":[{"id":"sk1","type":"sketch","plane":"Top Plane","entities":[{"type":"rectangle","x1_mm":-25,"y1_mm":-20,"x2_mm":25,"y2_mm":20}],"named_dims":[{"name":"length","value_mm":50},{"name":"width","value_mm":40}]},{"id":"f1","type":"extrude_boss","profile_id":"sk1","depth_mm":30,"name":"Base"}]}
"""


_REPAIR_ADDENDUM = """
════════════════════════════════════════
REPAIR MODE — execution error detected
════════════════════════════════════════
The previous OperationGraph was rejected by the SolidWorks executor with the error shown
in the conversation history. You MUST:
1. Read the exact ERROR or RULE VIOLATION message from the prior assistant turn.
2. Identify which operation caused the failure.
3. Emit a corrected OperationGraph that avoids the same error.
   Common fixes:
   - "Could not select top face" → change face_of to "Top Plane" (standard plane always works)
   - "Depth must be positive" → use a positive depth_mm value
   - "circular_pattern count must be >= 2" → ensure count >= 2
   - "missing position" → add at least one position to hole_wizard.positions
4. Do NOT repeat the exact same operations. Change the problematic parameter.
"""


def _has_execution_error(history: list[ConversationMessage] | None) -> bool:
    """Returns True if the most recent assistant message contains an executor error."""
    if not history:
        return False
    for msg in reversed(history):
        if msg.role == "assistant":
            return "ERROR:" in msg.content or "RULE VIOLATION" in msg.content
    return False


def _trim_history(history: list[ConversationMessage] | None) -> list[ConversationMessage]:
    """
    Server-side defense against old add-in builds or custom clients sending
    full runtime reports. Keep the latest turns and cap each message.
    """
    if not history:
        return []

    trimmed: list[ConversationMessage] = []
    for msg in history[-_MAX_HISTORY_MESSAGES:]:
        content = msg.content
        if len(content) > _MAX_HISTORY_CHARS:
            content = content[:_MAX_HISTORY_CHARS] + "\n... [history truncated]"
        trimmed.append(ConversationMessage(role=msg.role, content=content))
    return trimmed


def _build_context_block(ctx: DocumentContext, rag_context: str = "") -> str:
    lines = [
        f"Active Document Type : {ctx.document_type}",
        f"Solid Body Count     : {ctx.body_count}",
        f"File Path            : {ctx.file_path or 'Unsaved / new document'}",
        f"Selected Entities    : {', '.join(ctx.selected_ids) if ctx.selected_ids else 'None'}",
    ]
    if rag_context:
        lines += ["", "--- Engineering Standards / RAG Context ---", rag_context]
    return "\n".join(lines)


def _extract_json_object(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        last_fence    = text.rfind("```")
        if first_newline >= 0 and last_fence > first_newline:
            text = text[first_newline + 1:last_fence].strip()

    start = text.find("{")
    end   = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("LLM response did not contain a JSON object.")

    return json.loads(text[start:end + 1])


def _rate_limit_delay_seconds(exc: APIStatusError) -> float:
    retry_after = exc.response.headers.get("retry-after")
    if retry_after:
        try:
            return min(max(float(retry_after), 0.5), 8.0)
        except ValueError:
            pass

    match = re.search(r"try again in\s+([0-9.]+)s", exc.response.text, re.IGNORECASE)
    if match:
        return min(max(float(match.group(1)) + 0.25, 0.5), 8.0)
    return 1.5


def build_user_message(
    prompt: str,
    ctx: DocumentContext,
    rag_context: str = "",
) -> str:
    """
    Assemble the LLM user message from prompt + deterministic standards block
    + SolidWorks document context + (optional) RAG context. Pure function so
    the budget can be asserted in tests without touching the Groq client.
    """
    standards_block, _refs = build_standards_context(prompt)
    return (
        f"Request:\n{prompt}\n\n"
        + (f"{standards_block}\n\n" if standards_block else "")
        + f"SolidWorks Context:\n{_build_context_block(ctx, rag_context)}"
    )


def build_system_prompt(
    conversation_history: list[ConversationMessage] | None = None,
) -> str:
    """Return the system prompt, with the repair addendum appended when the
    previous assistant turn contains an execution error."""
    if _has_execution_error(conversation_history):
        return _SYSTEM_PROMPT + _REPAIR_ADDENDUM
    return _SYSTEM_PROMPT


class MacroEngineerAgent:
    def __init__(self) -> None:
        self._client = Groq(api_key=settings.groq_api_key, timeout=60.0, max_retries=0)

    def generate(
        self,
        prompt: str,
        ctx: DocumentContext,
        rag_context: str = "",
        conversation_history: list[ConversationMessage] | None = None,
    ) -> OperationGraph:
        conversation_history = _trim_history(conversation_history)
        user_message = build_user_message(prompt, ctx, rag_context)
        system = build_system_prompt(conversation_history)
        messages: list[dict] = [{"role": "system", "content": system}]

        # Inject prior turns so the LLM can see previous dimensions and op IDs.
        for msg in (conversation_history or []):
            messages.append({"role": msg.role, "content": msg.content})

        messages.append({"role": "user", "content": user_message})

        last_error: Exception | None = None
        for attempt in range(2):
            for rate_attempt in range(_MAX_RATE_LIMIT_RETRIES + 1):
                try:
                    completion = self._client.chat.completions.create(
                        model=settings.groq_model,
                        messages=messages,
                        temperature=0.0,
                        max_tokens=_LLM_MAX_TOKENS,
                        response_format={"type": "json_object"},
                    )
                    break
                except APIStatusError as exc:
                    if exc.status_code != 429 or rate_attempt >= _MAX_RATE_LIMIT_RETRIES:
                        raise
                    time.sleep(_rate_limit_delay_seconds(exc))

            content = completion.choices[0].message.content or ""
            try:
                return OperationGraph.model_validate(_extract_json_object(content))
            except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                last_error = exc
                if attempt == 0:
                    messages.append({"role": "assistant", "content": content})
                    messages.append({
                        "role": "user",
                        "content": (
                            f"Your response failed schema validation: {exc}. "
                            "Output only a corrected OperationGraph JSON object. "
                            "No prose, no explanation."
                        ),
                    })

        raise ValueError(
            f"LLM returned invalid OperationGraph JSON after 2 attempts: {last_error}"
        ) from last_error
