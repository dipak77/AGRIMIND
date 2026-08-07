"""Retrieval service for GraphRAG, Vector RAG, and Hybrid retrieval.

Implements multiple retrieval modes with citation enforcement.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class RetrievalMode(StrEnum):
    """Retrieval mode selection."""
    GRAPH = "graph"
    VECTOR = "vector"
    HYBRID = "hybrid"
    API = "api"
    AUTO = "auto"


class ChunkWithCitation(BaseModel):
    """Retrieved chunk with citation metadata."""

    chunk_id: str
    content: str
    score: float
    source_id: str
    source_type: str
    url_or_path: str
    checksum: str
    lang: str
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class GraphPathResult(BaseModel):
    """Result from graph traversal."""

    path_id: str
    start_node: str
    end_node: str
    nodes: list[dict[str, str]]
    relationships: list[dict[str, str]]
    confidence: float
    citations: list[str]
    is_approved: bool = True

    class Config:
        arbitrary_types_allowed = True


class RetrievalTrace(BaseModel):
    """Trace of retrieval operations for observability."""

    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    mode: RetrievalMode
    query: str
    filters: dict[str, str] = Field(default_factory=dict)
    graph_results_count: int = 0
    vector_results_count: int = 0
    api_results_count: int = 0
    reranking_applied: bool = False
    cache_hit: bool = False
    total_latency_ms: float = 0.0
    graph_latency_ms: float = 0.0
    vector_latency_ms: float = 0.0
    api_latency_ms: float = 0.0


class RetrievalRequest(BaseModel):
    """Request for retrieval operation."""

    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    query: str
    lang: str
    mode: RetrievalMode = RetrievalMode.AUTO
    top_k: int = 8
    filters: dict[str, str] = Field(default_factory=dict)
    require_citations: bool = True
    min_confidence: float = 0.7
    include_trace: bool = True

    class Config:
        arbitrary_types_allowed = True


class RetrievalResult(BaseModel):
    """Result from retrieval operation."""

    request_id: str
    query: str
    chunks: list[ChunkWithCitation] = Field(default_factory=list)
    graph_paths: list[GraphPathResult] = Field(default_factory=list)
    confidence: float = 0.0
    trace: RetrievalTrace | None = None
    has_citations: bool = True
    requires_approval: bool = False

    @property
    def result_count(self) -> int:
        """Total number of results."""
        return len(self.chunks) + len(self.graph_paths)

    def has_high_risk_content(self) -> bool:
        """Check if results contain high-risk content requiring approval."""
        for chunk in self.chunks:
            if chunk.metadata.get("safety_critical", False):
                return True
        for path in self.graph_paths:
            if not path.is_approved:
                return True
        return False

    class Config:
        arbitrary_types_allowed = True


class RetrievalConfig(BaseModel):
    """Configuration for retrieval service."""

    default_mode: RetrievalMode = RetrievalMode.HYBRID
    default_top_k: int = 8
    max_top_k: int = 50
    min_confidence_threshold: float = 0.5
    graph_enabled: bool = True
    vector_enabled: bool = True
    api_enabled: bool = True
    semantic_cache_enabled: bool = True
    semantic_cache_ttl_seconds: int = 3600
    reranking_enabled: bool = True
    reranker_model: str = "cross-encoder-multilingual"
    timeout_ms: int = 3000
    p95_latency_target_ms: float = 300.0

    class Config:
        frozen = True
