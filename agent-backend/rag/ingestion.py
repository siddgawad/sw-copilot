import re
import uuid
from pathlib import Path
from rag.vector_store import VectorStore


# ── Chunking strategies ────────────────────────────────────────────────────────

def _chunk_by_sections(text: str, source_name: str) -> list[dict]:
    """
    Split markdown by ## or ### headings so each section is its own retrievable chunk.
    Prepends the heading to every chunk so queries land on the right section.
    Falls back to character chunking if no headings are found.
    """
    sections = re.split(r"\n(?=## )", text)
    chunks = []
    for section in sections:
        section = section.strip()
        if not section:
            continue
        # Sub-split very long sections (>1200 chars) with overlap
        if len(section) > 1200:
            chunks.extend(_chunk_characters(section, 1000, 150))
        else:
            chunks.append(section)
    return [{"id": str(uuid.uuid4()), "text": c, "source": source_name} for c in chunks if c]


def _chunk_characters(text: str, chunk_size: int = 900, overlap: int = 120) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(text):
        chunk = text[start : start + chunk_size].strip()
        if chunk:
            chunks.append(chunk)
        start += chunk_size - overlap
    return chunks


# ── Ingesters per file type ────────────────────────────────────────────────────

def ingest_pdf(pdf_path: str | Path, store: VectorStore | None = None) -> int:
    from pypdf import PdfReader
    if store is None:
        store = VectorStore()
    reader    = PdfReader(str(pdf_path))
    full_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    source    = Path(pdf_path).name
    docs = [
        {"id": str(uuid.uuid4()), "text": c, "source": source}
        for c in _chunk_characters(full_text)
        if c
    ]
    store.add_documents(docs)
    return len(docs)


def ingest_markdown(md_path: str | Path, store: VectorStore | None = None) -> int:
    if store is None:
        store = VectorStore()
    text = Path(md_path).read_text(encoding="utf-8")
    docs = _chunk_by_sections(text, Path(md_path).name)
    store.add_documents(docs)
    return len(docs)


def ingest_text(txt_path: str | Path, store: VectorStore | None = None) -> int:
    if store is None:
        store = VectorStore()
    text  = Path(txt_path).read_text(encoding="utf-8")
    source = Path(txt_path).name
    docs  = [
        {"id": str(uuid.uuid4()), "text": c, "source": source}
        for c in _chunk_characters(text)
        if c
    ]
    store.add_documents(docs)
    return len(docs)


# ── Directory ingestion ────────────────────────────────────────────────────────

def ingest_directory(dir_path: str | Path) -> dict[str, int]:
    """
    Recursively ingest all supported files under dir_path.
    Supported: .pdf, .md, .txt
    Returns {filename: chunk_count}.
    """
    store   = VectorStore()
    results: dict[str, int] = {}
    base    = Path(dir_path)

    for pdf in base.glob("**/*.pdf"):
        results[pdf.name] = ingest_pdf(pdf, store)

    for md in base.glob("**/*.md"):
        results[md.name] = ingest_markdown(md, store)

    for txt in base.glob("**/*.txt"):
        results[txt.name] = ingest_text(txt, store)

    return results


def ingest_knowledge_base() -> dict[str, int]:
    """
    Ingest the built-in knowledge/ directory that ships with the backend.
    Called at startup when the vector store is empty.
    """
    knowledge_dir = Path(__file__).parent.parent / "knowledge"
    if not knowledge_dir.exists():
        return {}
    return ingest_directory(knowledge_dir)
