from __future__ import annotations

from agents.macro_engineer import build_system_prompt, build_user_message
from agents.rag_agent import RagAgent, _RAG_OUTPUT_CHAR_CAP
from models.schemas import ConversationMessage, DocumentContext
from standards.dimension_resolver import build_standards_context


def _ctx() -> DocumentContext:
    return DocumentContext(
        document_type="Part",
        body_count=1,
        selected_ids=[],
        file_path="test_part.sldprt",
    )


def test_simple_primitive_user_message_stays_small_without_rag():
    message = build_user_message(
        "create a 50mm x 40mm x 30mm box",
        _ctx(),
        rag_context="",
    )

    assert len(message) < 750
    assert "Engineering Standards / RAG Context" not in message
    assert "RESOLVED STANDARDS DATA" not in message


def test_fastener_prompt_keeps_deterministic_standards_context():
    message = build_user_message(
        "add four M6 counterbore holes at the corners",
        _ctx(),
        rag_context="",
    )

    assert "RESOLVED STANDARDS DATA" in message
    assert "M6 fastener" in message
    assert "ISO 273" in message
    assert "ISO 4762" in message
    assert "Clearance hole (normal fit): 6.6 mm" in message
    assert "Counterbore diameter: 11.0 mm" in message


def test_standards_context_caps_long_fastener_lists():
    block, refs = build_standards_context(
        "design holes for M3 M4 M5 M6 M8 M10 fasteners"
    )

    assert "M3 fastener" in block
    assert "M4 fastener" in block
    assert "M5 fastener" in block
    assert "M6 fastener" not in block
    assert len(refs) > 0


def test_repair_addendum_triggers_from_latest_assistant_error():
    system = build_system_prompt([
        ConversationMessage(role="user", content="make a box"),
        ConversationMessage(
            role="assistant",
            content="Runtime:\nERROR: synthetic executor failure",
        ),
    ])

    assert "REPAIR MODE" in system
    assert "execution error detected" in system


def test_repair_addendum_ignores_stale_error_if_latest_assistant_succeeded():
    system = build_system_prompt([
        ConversationMessage(role="assistant", content="ERROR: old failure"),
        ConversationMessage(role="user", content="try again"),
        ConversationMessage(role="assistant", content="Runtime:\nOK"),
    ])

    assert "REPAIR MODE" not in system


class _FakeStore:
    document_count = 37

    def __init__(self) -> None:
        self.last_n_results: int | None = None

    def query(self, prompt: str, n_results: int):
        self.last_n_results = n_results
        return [
            {"source": f"doc{i}.md", "text": "A" * 2500}
            for i in range(n_results)
        ]


def test_rag_skips_simple_primitive_prompts():
    agent = RagAgent.__new__(RagAgent)
    agent._store = _FakeStore()

    assert agent.is_relevant("create a 50mm x 40mm x 30mm box") is False
    assert agent.is_relevant("add four M6 counterbore holes") is True


def test_rag_retrieve_caps_chunks_and_output_size():
    agent = RagAgent.__new__(RagAgent)
    store = _FakeStore()
    agent._store = store

    context, sources = agent.retrieve("add M6 counterbore holes")

    assert store.last_n_results == 2
    assert len(context) <= _RAG_OUTPUT_CHAR_CAP + len("\n... [truncated]")
    assert sources == ["doc0.md", "doc1.md"]
