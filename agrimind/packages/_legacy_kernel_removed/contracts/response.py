"""
Response contract for AGRIMIND.

Defines the standard structure for all system responses to farmer queries.
Every response must include citations and confidence metadata for explainability.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar
from uuid import UUID

from pydantic import BaseModel, Field


class Citation(BaseModel):
    """
    Citation for a piece of information in the response.

    Every citation must trace back to a verified source with provenance.
    """

    source_id: str = Field(..., description="Unique identifier for the source")
    source_type: str = Field(
        ...,
        description="Type of source: document, knowledge_graph, api, expert",
    )
    url_or_path: str = Field(..., description="URL or file path to the source")
    checksum: str = Field(..., description="SHA-256 checksum of the source content")
    span: str | None = Field(None, description="Specific text span or section referenced")
    license: str | None = Field(None, description="License of the source")
    retrieved_at: datetime = Field(
        default_factory=datetime.utcnow, description="When this was retrieved"
    )

    class Config:
        json_schema_extra: ClassVar[dict[str, Any]] = {
            "example": {
                "source_id": "icar-cotton-manual-2024",
                "source_type": "document",
                "url_or_path": "s3://agrimind-data/curated/icar-cotton-manual.pdf",
                "checksum": "sha256:abc123...",
                "span": "Section 4.2: Bollworm Management",
                "license": "CC-BY-4.0",
            }
        }


class ResponseMetadata(BaseModel):
    """Additional metadata about the response generation."""

    model_version: str = Field(..., description="Model version used for generation")
    trace_id: str = Field(..., description="Distributed trace ID")
    retrieval_mode: str = Field(
        default="auto", description="Retrieval mode used: graph, vector, hybrid, api"
    )
    tool_calls: list[str] = Field(default_factory=list, description="List of tools called")
    latency_ms: int = Field(..., ge=0, description="Total latency in milliseconds")
    token_usage: dict[str, int] | None = Field(None, description="Token usage statistics")


class Response(BaseModel):
    """
    Standard response contract for all farmer interactions.

    Every response must include:
    - The answer in the requested language
    - Citations for factual claims
    - Confidence score
    - Model version and trace ID for observability
    """

    query_id: UUID = Field(..., description="Reference to the original query")
    answer: str = Field(..., min_length=1, description="Response text in requested language")
    lang: str = Field(..., pattern="^(en|hi|mr)$", description="Language code of the response")
    citations: list[Citation] = Field(
        default_factory=list, description="Sources cited in the response"
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score (0.0 to 1.0)")
    model_version: str = Field(..., description="Model version used")
    trace_id: str = Field(..., description="Distributed trace ID")
    metadata: ResponseMetadata | None = Field(None, description="Additional response metadata")
    safety_flags: list[str] = Field(default_factory=list, description="Any safety flags raised")
    fallback_used: bool = Field(default=False, description="Whether a fallback mechanism was used")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")

    class Config:
        json_schema_extra: ClassVar[dict[str, Any]] = {
            "example": {
                "query_id": "550e8400-e29b-41d4-a716-446655440000",
                "answer": "कपाशीवरील बोंडअळी नियंत्रणासाठी एकात्मिक कीटक व्यवस्थापन (IPM) पद्धती वापराव्यात...",
                "lang": "mr",
                "citations": [
                    {
                        "source_id": "icar-cotton-manual-2024",
                        "source_type": "document",
                        "url_or_path": "s3://agrimind-data/curated/icar-cotton-manual.pdf",
                        "checksum": "sha256:abc123...",
                        "span": "Section 4.2",
                    }
                ],
                "confidence": 0.92,
                "model_version": "agrimind-7b-v1.0.3",
                "trace_id": "0123456789abcdef",
            }
        }

    @property
    def has_citations(self) -> bool:
        """Check if response includes citations."""
        return len(self.citations) > 0

    @property
    def is_high_confidence(self) -> bool:
        """Check if response meets high confidence threshold."""
        return self.confidence >= 0.85

    @property
    def requires_review(self) -> bool:
        """Check if response should be flagged for expert review."""
        return self.confidence < 0.70 or len(self.safety_flags) > 0
