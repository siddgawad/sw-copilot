import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
from config import settings


class VectorStore:
    """
    Thin wrapper around ChromaDB.

    The embedding function (ONNX MiniLM — no torch dependency) is lazy-initialized
    on first query or ingest so that server startup and /health checks are instant.
    """

    def __init__(self) -> None:
        self._client = chromadb.PersistentClient(
            path=settings.chroma_persist_dir,
            settings=ChromaSettings(
                anonymized_telemetry=False,
                chroma_product_telemetry_impl="rag.noop_telemetry.NoOpProductTelemetryClient",
            ),
        )
        self._collection = None  # lazy — avoids loading ONNX model at startup

    def _get_collection(self):
        if self._collection is None:
            self._collection = self._client.get_or_create_collection(
                name=settings.chroma_collection_name,
                embedding_function=DefaultEmbeddingFunction(),
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def add_documents(self, documents: list[dict]) -> None:
        """documents: list of {"id": str, "text": str, "source": str}"""
        self._get_collection().upsert(
            ids       =[d["id"]     for d in documents],
            documents =[d["text"]   for d in documents],
            metadatas =[{"source": d["source"]} for d in documents],
        )

    def query(self, query_text: str, n_results: int = 5) -> list[dict]:
        """Returns list of {"text": str, "source": str} sorted by relevance."""
        results = self._get_collection().query(
            query_texts=[query_text],
            n_results=n_results,
            include=["documents", "metadatas"],
        )
        out: list[dict] = []
        for text, meta in zip(results["documents"][0], results["metadatas"][0]):
            out.append({"text": text, "source": meta.get("source", "unknown")})
        return out

    @property
    def document_count(self) -> int:
        try:
            # get_collection (no EF needed) avoids triggering model load for /health checks.
            c = self._client.get_collection(name=settings.chroma_collection_name)
            return c.count()
        except Exception:
            return 0
