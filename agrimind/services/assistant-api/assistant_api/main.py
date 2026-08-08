"""Assistant API — farmer chat + flywheel feedback capture (E1)."""

from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from typing import Literal

import httpx
import structlog
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from agrimind_kernel.config.settings import get_settings
from agrimind_kernel.contracts import Citation, GeoPoint, Language, Query, QueryModality
from agrimind_kernel.feedback.events import (
    FeedbackEvent,
    FeedbackType,
    build_feedback_store,
    capture_response_signals,
)
from agrimind_kernel.safety_engine import SafetyEngine
from agrimind_kernel.security.pii import PIIRedactor

logger = structlog.get_logger()
settings = get_settings()
safety = SafetyEngine()
pii = PIIRedactor()


class ChatRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4096)
    lang: Literal["en", "hi", "mr"] = "en"
    modality: Literal["text", "voice", "image", "multi"] = "text"
    location: GeoPoint | None = None
    user_id: str = Field(default_factory=lambda: f"farmer_{uuid.uuid4().hex[:8]}")


class ChatResponse(BaseModel):
    query_id: str
    answer: str
    lang: str
    citations: list[Citation] = []
    confidence: float
    model_version: str
    trace_id: str
    intent: str | None = None
    safety_flags: list[str] = []
    fallback_used: bool = False
    requires_review: bool = False
    action: str = "answer"
    flywheel_events: list[str] = []


class ThumbsFeedback(BaseModel):
    query_id: str | None = None
    user_id: str | None = None
    query_text: str = ""
    answer_text: str = ""
    vote: Literal["up", "down"]
    reason: str | None = None
    confidence: float | None = None
    intent: str | None = None
    model_version: str | None = None
    trace_id: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    from agrimind_kernel.telemetry.otel import setup_otel

    setup_otel(
        "assistant-api",
        otlp_endpoint=os.getenv(
            "OTEL_EXPORTER_OTLP_ENDPOINT", settings.otel_exporter_otlp_endpoint
        ),
    )
    logger.info("assistant-api starting", orchestrator=settings.agent_orchestrator_url)
    app.state.http = httpx.AsyncClient(timeout=90.0)
    # FEEDBACK_STORE=auto|postgres|jsonl|memory (auto tries Postgres, falls back to JSONL)
    backend = os.getenv("FEEDBACK_STORE", settings.feedback_store)
    path = os.getenv("FEEDBACK_PATH", settings.feedback_path)
    dsn = os.getenv("POSTGRES_DSN", settings.postgres_dsn)
    app.state.feedback = build_feedback_store(backend=backend, path=path, dsn=dsn)
    yield
    await app.state.http.aclose()


app = FastAPI(title="AGRIMIND Assistant API", version="0.2.0", lifespan=lifespan)

# F2: request spans + trace header propagation
from agrimind_kernel.telemetry.otel import instrument_fastapi  # noqa: E402

instrument_fastapi(app, "assistant-api")


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "assistant-api", "version": "0.2.0"}


@app.get("/ready")
async def ready():
    return {"status": "ready", "orchestrator": settings.agent_orchestrator_url}


@app.post("/v1/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    x_request_id: str | None = Header(None),
):
    request_id = x_request_id or str(uuid.uuid4())
    redacted_text, pii_flags = pii.redact(request.text)

    query = Query(
        text=redacted_text,
        lang=Language(request.lang),
        modality=QueryModality(request.modality),
        location=request.location,
        user_id=request.user_id,
    )

    logger.info(
        "query_received",
        query_id=str(query.query_id),
        lang=request.lang,
        pii_flags=pii_flags,
        request_id=request_id,
    )

    client: httpx.AsyncClient = app.state.http
    payload = {
        "query_id": str(query.query_id),
        "text": query.text,
        "lang": request.lang,
        "modality": request.modality,
        "user_id": query.user_id,
        "location": request.location.model_dump() if request.location else None,
    }
    headers = {"X-Request-ID": request_id, "Content-Type": "application/json"}

    try:
        resp = await client.post(
            f"{settings.agent_orchestrator_url}/v1/run",
            json=payload,
            headers=headers,
        )
    except httpx.RequestError as exc:
        logger.error("orchestrator_unreachable", error=str(exc))
        fb = safety.create_safe_fallback_response(
            query, trace_id=request_id, reasons=["orchestrator_down"]
        )
        flywheel = capture_response_signals(
            app.state.feedback,
            query_id=str(query.query_id),
            user_id=request.user_id,
            query_text=query.text,
            answer_text=fb.answer,
            confidence=fb.confidence,
            intent=None,
            model_version=fb.model_version,
            trace_id=request_id,
            fallback_used=True,
            requires_review=True,
        )
        return ChatResponse(
            query_id=str(query.query_id),
            answer=fb.answer,
            lang=request.lang,
            citations=[],
            confidence=fb.confidence,
            model_version=fb.model_version,
            trace_id=request_id,
            safety_flags=["orchestrator_unreachable"],
            fallback_used=True,
            requires_review=True,
            action="fallback_human",
            flywheel_events=[e.event_id for e in flywheel],
        )

    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"orchestrator error: {resp.text}")

    data = resp.json()
    confidence = float(data.get("confidence", 0.0))
    fallback = bool(data.get("fallback_used", False))
    requires_review = bool(data.get("requires_review", False))
    answer = data["answer"]
    flywheel = capture_response_signals(
        app.state.feedback,
        query_id=str(data.get("query_id", query.query_id)),
        user_id=request.user_id,
        query_text=query.text,
        answer_text=answer,
        confidence=confidence,
        intent=data.get("intent"),
        model_version=data.get("model_version"),
        trace_id=data.get("trace_id", request_id),
        fallback_used=fallback,
        requires_review=requires_review,
    )
    return ChatResponse(
        query_id=str(data.get("query_id", query.query_id)),
        answer=answer,
        lang=data.get("lang", request.lang),
        citations=[Citation.model_validate(c) for c in data.get("citations", [])],
        confidence=confidence,
        model_version=data.get("model_version", "unknown"),
        trace_id=data.get("trace_id", request_id),
        intent=data.get("intent"),
        safety_flags=data.get("safety_flags", []),
        fallback_used=fallback,
        requires_review=requires_review,
        action=data.get("action", "answer"),
        flywheel_events=[e.event_id for e in flywheel],
    )


@app.post("/v1/feedback")
async def thumbs_feedback(body: ThumbsFeedback):
    """Farmer thumbs up/down → flywheel store (E1)."""
    ftype = (
        FeedbackType.THUMBS_UP.value
        if body.vote == "up"
        else FeedbackType.THUMBS_DOWN.value
    )
    event = FeedbackEvent(
        feedback_type=ftype,
        query_id=body.query_id,
        user_id=body.user_id,
        query_text=body.query_text,
        answer_text=body.answer_text[:2000],
        confidence=body.confidence,
        intent=body.intent,
        model_version=body.model_version,
        trace_id=body.trace_id,
        reason=body.reason or f"thumbs_{body.vote}",
    )
    app.state.feedback.append(event)
    logger.info("feedback_recorded", type=ftype, event_id=event.event_id)
    return {"status": "ok", "event": event.to_dict()}


@app.get("/v1/feedback/stats")
async def feedback_stats():
    return {
        "counts": app.state.feedback.count_by_type(),
        "backend": type(app.state.feedback).__name__,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
