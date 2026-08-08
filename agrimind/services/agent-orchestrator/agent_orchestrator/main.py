"""Agent Orchestrator — runs bounded agent graph; calls memory + inference over HTTP."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any, Literal

import httpx
import structlog
from fastapi import FastAPI, Header
from pydantic import BaseModel, Field

from agents.graphs.orchestrator import run_agent_async, state_to_response
from agrimind_kernel.config.settings import get_settings
from agrimind_kernel.contracts import GeoPoint, Language, Query, QueryModality

logger = structlog.get_logger()
settings = get_settings()


class RunRequest(BaseModel):
    query_id: str | None = None
    text: str = Field(..., min_length=1)
    lang: Literal["en", "hi", "mr"] = "en"
    modality: Literal["text", "voice", "image", "multi"] = "text"
    user_id: str = "farmer_unknown"
    location: GeoPoint | None = None


class RunResponse(BaseModel):
    query_id: str
    answer: str
    lang: str
    citations: list[dict[str, Any]] = []
    confidence: float
    model_version: str
    trace_id: str
    intent: str | None = None
    safety_flags: list[str] = []
    fallback_used: bool = False
    requires_review: bool = False
    action: str = "answer"
    safety_level: str | None = None
    retrieval_backend: str | None = None
    generation_backend: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    import os

    from agrimind_kernel.telemetry.otel import setup_otel

    setup_otel(
        "agent-orchestrator",
        otlp_endpoint=os.getenv(
            "OTEL_EXPORTER_OTLP_ENDPOINT", settings.otel_exporter_otlp_endpoint
        ),
    )
    logger.info(
        "agent-orchestrator starting",
        memory=settings.memory_service_url,
        inference=settings.inference_service_url,
    )
    app.state.http = httpx.AsyncClient(timeout=60.0)
    yield
    await app.state.http.aclose()
    logger.info("agent-orchestrator stopped")


app = FastAPI(title="agent-orchestrator", version="0.1.0", lifespan=lifespan)

from agrimind_kernel.telemetry.otel import instrument_fastapi  # noqa: E402

instrument_fastapi(app, "agent-orchestrator")


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "agent-orchestrator", "version": "0.1.0"}


@app.get("/ready")
async def ready():
    return {
        "status": "ready",
        "memory_service_url": settings.memory_service_url,
        "inference_service_url": settings.inference_service_url,
    }


@app.post("/v1/run", response_model=RunResponse)
async def run(req: RunRequest, x_request_id: str | None = Header(None)):
    trace_id = x_request_id or str(uuid.uuid4())
    qid = uuid.UUID(req.query_id) if req.query_id else uuid.uuid4()
    query = Query(
        query_id=qid,
        text=req.text,
        lang=Language(req.lang),
        modality=QueryModality(req.modality),
        user_id=req.user_id,
        location=req.location,
    )

    # Prefer HTTP to memory + inference; local fallback only in local/dev/test
    state = await run_agent_async(
        query,
        trace_id=trace_id,
        memory_url=settings.memory_service_url,
        inference_url=settings.inference_service_url,
        allow_local_fallback=settings.env.lower() in ("local", "dev", "test"),
        http_client=app.state.http,
        headers={"X-Request-ID": trace_id},
    )
    response = state_to_response(state)
    retrieval = state.get("retrieval_results") or {}
    logger.info(
        "agent_run_complete",
        query_id=str(query.query_id),
        intent=state.get("intent"),
        confidence=state.get("confidence"),
        fallback=state.get("fallback_used"),
        retrieval_backend=retrieval.get("_backend") if isinstance(retrieval, dict) else None,
        generation_backend=retrieval.get("_generation_backend")
        if isinstance(retrieval, dict)
        else None,
        trace_id=trace_id,
    )
    return RunResponse(
        query_id=str(response.query_id),
        answer=response.answer,
        lang=str(response.lang.value if hasattr(response.lang, "value") else response.lang),
        citations=[c.model_dump(mode="json") for c in response.citations],
        confidence=response.confidence,
        model_version=response.model_version,
        trace_id=response.trace_id,
        intent=response.intent,
        safety_flags=response.safety_flags,
        fallback_used=response.fallback_used,
        requires_review=response.requires_review,
        action=response.action,
        safety_level=response.safety_level.value,
        retrieval_backend=response.metadata.get("retrieval_backend"),
        generation_backend=response.metadata.get("generation_backend"),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8002)
