"""Assistant API - Main FastAPI Application for Farmer Queries."""
import uuid
from contextlib import asynccontextmanager
from typing import Optional, Literal
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel, Field
import structlog
from agrimind_kernel.config.settings import get_settings
from agrimind_kernel.contracts.query import Query, GeoPoint
from agrimind_kernel.contracts.response import Response, Citation
from agrimind_kernel.telemetry.tracing import TraceContext

logger = structlog.get_logger()
settings = get_settings()


class ChatRequest(BaseModel):
    text: str
    lang: Literal["en", "hi", "mr"] = "en"
    modality: Literal["text", "voice", "image", "multi"] = "text"
    location: Optional[GeoPoint] = None
    user_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class ChatResponse(BaseModel):
    query_id: str
    answer: str
    lang: str
    citations: list[Citation] = []
    confidence: float
    model_version: str
    trace_id: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Assistant API service starting up")
    yield
    logger.info("Assistant API service shutting down")


app = FastAPI(title="AGRIMIND Assistant API", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "assistant-api"}


@app.post("/v1/chat", response_model=ChatResponse)
async def chat_endpoint(
    request: ChatRequest,
    x_request_id: Optional[str] = Header(None),
):
    request_id = x_request_id or str(uuid.uuid4())
    trace_ctx = TraceContext(request_id=request_id, span_id=str(uuid.uuid4()))
    
    query = Query(
        query_id=uuid.UUID(request_id),
        text=request.text,
        lang=request.lang,
        modality=request.modality,
        location=request.location,
        user_id=request.user_id,
    )
    
    logger.info(
        "query_received",
        query_id=request_id,
        lang=request.lang,
        modality=request.modality,
    )
    
    # Mock response for now - will be connected to agent orchestrator
    response = ChatResponse(
        query_id=request_id,
        answer=f"Received your {request.lang} query about agriculture. This is a placeholder response.",
        lang=request.lang,
        citations=[],
        confidence=0.95,
        model_version="agrimind-7b-v1.0.0",
        trace_id=request_id,
    )
    
    return response


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
