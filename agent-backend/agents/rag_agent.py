from rag.vector_store import VectorStore
from config import settings


class RagAgent:
    def __init__(self) -> None:
        self._store = VectorStore()

    def is_relevant(self, prompt: str) -> bool:
        # Always retrieve — every CAD request benefits from engineering standards context.
        # The semantic search will return low-relevance results for truly off-topic queries,
        # which the LLM will ignore.
        return self._store.document_count > 0

    def retrieve(self, prompt: str) -> tuple[str, list[str]]:
        """
        Returns (context_text, source_list).
        Retrieves up to 8 chunks; formats them clearly for LLM injection.
        """
        n = max(settings.max_rag_results, 8)
        results = self._store.query(prompt, n_results=n)
        if not results:
            return "", []

        sections = []
        for r in results:
            sections.append(f"[{r['source']}]\n{r['text']}")

        context_text = "\n\n---\n\n".join(sections)
        sources      = sorted({r["source"] for r in results})
        return context_text, sources
