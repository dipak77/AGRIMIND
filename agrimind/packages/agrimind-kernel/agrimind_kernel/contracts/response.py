"""Response and citation contracts with provenance."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from agrimind_kernel.contracts.query import Language
from agrimind_kernel.contracts.safety import SafetyLevel


class Citation(BaseModel):
    """Grounded citation with provenance (plan-aligned)."""

    source_id: str
    source_type: Literal["document", "knowledge_graph", "api", "expert", "web", "graph"] = (
        "document"
    )
    title: str = ""
    url_or_path: str = ""
    url: str | None = None
    checksum: str = ""
    span: str | None = None
    excerpt: str = ""
    license: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Response(BaseModel):
    """Canonical farmer-facing response."""

    response_id: str = Field(default_factory=lambda: str(UUID(int=0)))
    query_id: UUID | str
    answer: str = Field(..., min_length=1)
    lang: Language | str
    citations: list[Citation] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)
    model_version: str
    trace_id: str
    safety_level: SafetyLevel = SafetyLevel.GENERAL
    safety_flags: list[str] = Field(default_factory=list)
    requires_review: bool = False
    fallback_used: bool = False
    intent: str | None = None
    action: Literal["answer", "fallback_human", "refuse"] = "answer"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Back-compat alias used by some call sites / SafetyEngine
    @property
    def text(self) -> str:
        return self.answer

    @property
    def language(self) -> Language | str:
        return self.lang

    @property
    def has_citations(self) -> bool:
        return len(self.citations) > 0
