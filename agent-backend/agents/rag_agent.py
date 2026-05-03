import re

from rag.vector_store import VectorStore
from config import settings


# Keywords that justify retrieving engineering RAG context. If a prompt mentions
# none of these, it's a "simple primitive" request and we skip RAG entirely to
# stay inside the token budget. Standards (ISO 273/4762/...) already cover
# fastener dimensions through dimension_resolver.build_standards_context, so we
# don't need RAG just for "M6 hole" cases either — but the keyword set still
# matches them so RAG can layer on rationale (edge inset rules, fit guidance).
_COMPLEX_KEYWORDS = re.compile(
    r"\b("
    r"M\d|hole|counterbore|countersink|tap|tapped|thread|"
    r"fit|tolerance|H\d|h\d|GD&T|datum|"
    r"fillet|chamfer|edge|inset|wall|fastener|nut|washer|bolt|screw|"
    r"flange|bracket|housing|bearing|gear|spring|"
    r"steel|aluminium|aluminum|brass|plastic|material|mass|weight|"
    r"pattern|mirror|revolve|sweep|loft|shell|draft|rib|"
    r"plate|mounting|shaft|stepped"
    r")\b",
    re.IGNORECASE,
)

# Hard cap on RAG output to keep the user message inside the LLM context budget
# even for very long retrieved chunks.
_RAG_OUTPUT_CHAR_CAP = 6000


class RagAgent:
    def __init__(self) -> None:
        self._store = VectorStore()

    def is_relevant(self, prompt: str) -> bool:
        """
        Skip RAG for trivial primitive requests (e.g. "create a 50mm box") that
        do not mention any engineering concept that benefits from explanatory
        text. Standards-grounded numbers come from dimension_resolver, not RAG.
        """
        if self._store.document_count == 0:
            return False
        return bool(_COMPLEX_KEYWORDS.search(prompt))

    def retrieve(self, prompt: str) -> tuple[str, list[str]]:
        """
        Returns (context_text, source_list). Capped at 4 chunks (was 8) and
        truncated to _RAG_OUTPUT_CHAR_CAP characters. Empty when no chunks.
        """
        n = min(max(settings.max_rag_results, 1), 4)
        results = self._store.query(prompt, n_results=n)
        if not results:
            return "", []

        sections = [f"[{r['source']}]\n{r['text']}" for r in results]
        context_text = "\n\n---\n\n".join(sections)
        if len(context_text) > _RAG_OUTPUT_CHAR_CAP:
            context_text = context_text[:_RAG_OUTPUT_CHAR_CAP] + "\n... [truncated]"
        sources = sorted({r["source"] for r in results})
        return context_text, sources
