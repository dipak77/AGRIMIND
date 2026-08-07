"""Inference request/response contracts."""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid


class InferenceRequest(BaseModel):
    """Request for model inference."""
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    model_id: str
    prompt: str
    max_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 0.9
    stop_sequences: Optional[List[str]] = None
    structured_output: Optional[Dict[str, Any]] = None  # JSON schema for structured output
    stream: bool = False


class InferenceResponse(BaseModel):
    """Response from model inference."""
    request_id: str
    model_id: str
    completion: str
    finish_reason: str
    usage: Dict[str, int]  # prompt_tokens, completion_tokens, total_tokens
    latency_ms: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    warnings: Optional[List[str]] = None
