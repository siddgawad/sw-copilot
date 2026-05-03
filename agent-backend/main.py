import os
import re
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from groq import APIConnectionError, APIError, APIStatusError, APITimeoutError
from starlette.concurrency import run_in_threadpool

from agents.macro_engineer import MacroEngineerAgent
from agents.rag_agent import RagAgent
from agents.validation_agent import validate as validate_graph_against_report
from models.schemas import (
    DocumentContext, GenerateRequest, GenerateResponse,
    IngestResponse, OperationGraph,
    ValidateRequest, ValidationReport,
)
from config import settings

# ── Application-level singletons initialised once at startup ──────────────────

macro_agent: MacroEngineerAgent | None = None
rag_agent:   RagAgent           | None = None
backend_token: str | None = None

_INJECTION_PATTERN = re.compile(
    r"(RULE:|SYSTEM:|INSTRUCTION:|DEVELOPER:|ASSISTANT:|IGNORE\s+PREVIOUS|DISREGARD\s+PREVIOUS|<\|im_start\|>|<\|im_end\|>)",
    re.IGNORECASE,
)
_CONTROL_CHARS_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WHITESPACE_PATTERN = re.compile(r"\s+")


def _token_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        base = Path(local_app_data)
    else:
        base = Path.home() / "AppData" / "Local"
    return base / "SwCopilotAddin" / "backend.token"


def _write_backend_token() -> str:
    token = secrets.token_hex(32)
    path = _token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token, encoding="utf-8")
    return token


async def verify_token(x_copilot_token: str = Header(default="")) -> None:
    if not backend_token or not secrets.compare_digest(x_copilot_token, backend_token):
        raise HTTPException(status_code=403, detail="Invalid or missing X-Copilot-Token header.")


def _sanitize_context_value(value: object, max_length: int = 1024) -> str:
    if value is None:
        return ""

    sanitized = str(value)
    sanitized = sanitized.replace("\n", " ").replace("\r", " ").replace("`", "'")
    sanitized = _CONTROL_CHARS_PATTERN.sub(" ", sanitized)
    sanitized = _INJECTION_PATTERN.sub("[REDACTED]", sanitized)
    sanitized = _WHITESPACE_PATTERN.sub(" ", sanitized).strip()
    return sanitized[:max_length]


def _sanitize_context(ctx: DocumentContext) -> DocumentContext:
    return ctx.model_copy(
        update={
            "document_type": _sanitize_context_value(ctx.document_type),
            "selected_ids": [_sanitize_context_value(item) for item in ctx.selected_ids],
            "file_path": _sanitize_context_value(ctx.file_path),
        }
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    global macro_agent, rag_agent, backend_token
    backend_token = _write_backend_token()
    macro_agent = MacroEngineerAgent()
    rag_agent   = RagAgent()

    # Auto-ingest built-in knowledge base if the vector store is empty.
    if rag_agent._store.document_count == 0:
        from rag.ingestion import ingest_knowledge_base
        results = await run_in_threadpool(ingest_knowledge_base)
        total = sum(results.values())
        if total:
            import logging
            logging.getLogger("uvicorn").info(
                f"Knowledge base ingested: {len(results)} files, {total} chunks."
            )

    yield
    # teardown (none required for these stateless agents)


app = FastAPI(
    title="SW Copilot — Agent Backend",
    version="0.1.0",
    description="Receives natural-language prompts from the SolidWorks Add-in and returns executable C# macros.",
    lifespan=lifespan,
)

# ── Routes ────────────────────────────────────────────────────────────────────


@app.post("/generate", response_model=GenerateResponse, dependencies=[Depends(verify_token)])
async def generate(req: GenerateRequest) -> GenerateResponse:
    """
    Main endpoint called by the C# Add-in.
    1. Optionally retrieves engineering standards context from ChromaDB (RAG Agent).
    2. Passes the enriched prompt to the Macro Engineer Agent (Groq LLM).
    3. Returns the raw C# macro string to the Add-in for runtime compilation.
    """
    if macro_agent is None or rag_agent is None:
        raise HTTPException(status_code=503, detail="Agents not yet initialised.")

    sanitized_context = _sanitize_context(req.context)

    rag_context, rag_sources = "", []
    if rag_agent.is_relevant(req.prompt):
        rag_context, rag_sources = await run_in_threadpool(rag_agent.retrieve, req.prompt)

    try:
        operation_graph: OperationGraph = await run_in_threadpool(
            macro_agent.generate,
            req.prompt,
            sanitized_context,
            rag_context,
            req.messages,
        )
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except APITimeoutError as exc:
        raise HTTPException(status_code=504, detail="Groq request timed out.") from exc
    except APIConnectionError as exc:
        raise HTTPException(status_code=502, detail="Could not connect to Groq.") from exc
    except APIStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Groq API returned {exc.status_code}: {exc.response.text}",
        ) from exc
    except APIError as exc:
        raise HTTPException(status_code=502, detail=f"Groq API error: {exc}") from exc

    has_missing = bool(operation_graph.missing_inputs)
    status = (
        "Clarification needed — see missing inputs before executing."
        if has_missing
        else f"Plan ready: {len(operation_graph.operations)} operation(s) — review before executing."
    )

    return GenerateResponse(
        macro_code=None,
        cad_command=None,
        operation_graph=operation_graph,
        status_message=status,
        rag_sources=rag_sources,
    )


@app.post("/ingest", response_model=IngestResponse, dependencies=[Depends(verify_token)])
async def ingest(
    source_dir: str = Query(default="./standards", description="Directory containing engineering PDFs"),
) -> IngestResponse:
    """
    Walks source_dir, extracts text from every PDF, and upserts chunks into ChromaDB.
    Run once (or whenever the standards library is updated).
    """
    from rag.ingestion import ingest_directory

    results = ingest_directory(source_dir)
    return IngestResponse(
        ingested_files=len(results),
        total_chunks=sum(results.values()),
        detail=results,
    )


@app.post("/validate", response_model=ValidationReport, dependencies=[Depends(verify_token)])
async def validate(req: ValidateRequest) -> ValidationReport:
    """
    Compare a previously-generated OperationGraph (what was requested) against
    the PartReport returned by OperationExecutor.ExtractPartReport (what SW
    actually built). Returns a ValidationReport flagging any discrepancies in
    bounding box, body count, feature count, or suppressed features.
    """
    return validate_graph_against_report(
        req.operation_graph,
        req.part_report,
        tolerance_mm=req.tolerance_mm,
    )


@app.get("/version")
async def version() -> dict:
    """Version check — no auth required so the add-in can verify compatibility before startup."""
    from rag.vector_store import VectorStore
    store = VectorStore()
    return {
        "version":     "0.1.0",
        "backend":     "sw-copilot-agent-backend",
        "groq_model":  settings.groq_model,
        "vector_docs": store.document_count,
    }


@app.get("/health", dependencies=[Depends(verify_token)])
async def health() -> dict:
    from rag.vector_store import VectorStore
    store = VectorStore()
    return {
        "status":      "ok",
        "model":       settings.groq_model,
        "vector_docs": store.document_count,
    }
