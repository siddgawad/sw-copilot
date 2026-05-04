import os
import re
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from groq import APIConnectionError, APIError, APIStatusError, APITimeoutError
from starlette.concurrency import run_in_threadpool

from agents.base_plate_v0 import (
    try_compile_base_plate_v0,
    update_run_artifacts_after_validation,
    write_initial_run_artifacts,
)
from agents.macro_engineer import MacroEngineerAgent, try_fast_path_clarification
from agents.rag_agent import RagAgent
from agents.run_trace import make_trace_id, save_generate_trace, save_validation_trace
from agents.validation_agent import validate as validate_graph_against_report
from patterns.router import try_pattern_match
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
    description="Receives natural-language prompts from the SolidWorks Add-in and returns validated CAD OperationGraph JSON.",
    lifespan=lifespan,
)

# ── Routes ────────────────────────────────────────────────────────────────────


@app.post("/generate", response_model=GenerateResponse, dependencies=[Depends(verify_token)])
async def generate(req: GenerateRequest) -> GenerateResponse:
    """
    Main endpoint called by the C# Add-in.
    1. Optionally retrieves engineering standards context from ChromaDB (RAG Agent).
    2. Passes the enriched prompt to the Macro Engineer Agent/provider router.
    3. Returns a validated OperationGraph JSON object to the Add-in.
    """
    base_plate = try_compile_base_plate_v0(req.prompt)
    if base_plate is not None:
        trace_id, run_dir = write_initial_run_artifacts(req.prompt, base_plate)
        has_missing = bool(base_plate.operation_graph.missing_inputs)
        return GenerateResponse(
            macro_code=None,
            cad_command=None,
            operation_graph=base_plate.operation_graph,
            design_spec=base_plate.design_spec,
            coordinate_plan=base_plate.coordinate_plan,
            sketch_graph=base_plate.sketch_graph,
            trace_id=trace_id,
            run_artifact_path=str(run_dir),
            status_message=(
                "Unsupported base_plate_v0 request — see missing inputs."
                if has_missing
                else "base_plate_v0 deterministic plan ready — no LLM call required."
            ),
            rag_sources=[],
        )

    if macro_agent is None or rag_agent is None:
        raise HTTPException(status_code=503, detail="Agents not yet initialised.")

    sanitized_context = _sanitize_context(req.context)

    # ── Deterministic pattern library (runs before any LLM call) ─────────────
    pattern_graph = try_pattern_match(req.prompt)
    if pattern_graph is not None:
        has_missing = bool(pattern_graph.missing_inputs)
        trace_id = make_trace_id(pattern_graph.part_name)
        if not has_missing:
            await run_in_threadpool(
                save_generate_trace, trace_id, req.prompt, pattern_graph, "pattern"
            )
        return GenerateResponse(
            operation_graph=pattern_graph,
            trace_id=trace_id,
            status_message=(
                "Clarification needed — see missing inputs."
                if has_missing
                else f"Deterministic pattern: {pattern_graph.part_name or 'part'} — no LLM call required."
            ),
            rag_sources=[],
        )

    fast_path_graph = try_fast_path_clarification(req.prompt, req.messages)
    if fast_path_graph is not None:
        return GenerateResponse(
            macro_code=None,
            cad_command=None,
            operation_graph=fast_path_graph,
            status_message="Clarification needed — see missing inputs before executing.",
            rag_sources=[],
        )

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
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"LLM provider error: {exc}") from exc
    except APITimeoutError as exc:
        raise HTTPException(status_code=504, detail="LLM provider request timed out.") from exc
    except APIConnectionError as exc:
        raise HTTPException(status_code=502, detail="Could not connect to LLM provider.") from exc
    except APIStatusError as exc:
        if exc.status_code == 429:
            raise HTTPException(
                status_code=429,
                detail=f"LLM provider rate limit reached. Retry shortly. Provider response: {exc.response.text}",
            ) from exc
        raise HTTPException(
            status_code=502,
            detail=f"LLM provider returned {exc.status_code}: {exc.response.text}",
        ) from exc
    except APIError as exc:
        raise HTTPException(status_code=502, detail=f"LLM provider API error: {exc}") from exc

    has_missing = bool(operation_graph.missing_inputs)
    status = (
        "Clarification needed — see missing inputs before executing."
        if has_missing
        else f"Plan ready: {len(operation_graph.operations)} operation(s) — review before executing."
    )

    # Save run trace for every successful LLM call — this is the training dataset.
    trace_id = make_trace_id(operation_graph.part_name)
    if not has_missing:
        await run_in_threadpool(
            save_generate_trace, trace_id, req.prompt, operation_graph, "llm"
        )

    return GenerateResponse(
        macro_code=None,
        cad_command=None,
        operation_graph=operation_graph,
        trace_id=trace_id,
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
    report = validate_graph_against_report(
        req.operation_graph,
        req.part_report,
        tolerance_mm=req.tolerance_mm,
        executor_result=req.executor_result,
    )
    update_run_artifacts_after_validation(
        req.operation_graph,
        req.part_report,
        report,
        req.executor_result,
    )
    # Save validation artifacts — completes the run trace started at /generate time.
    if req.trace_id:
        await run_in_threadpool(
            save_validation_trace,
            req.trace_id,
            req.executor_result,
            req.part_report,
            report,
        )
    return report


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
