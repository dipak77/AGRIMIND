"""Multilingual embedding service for agricultural domain.

Supports BGE-Multilingual and E5-Multilingual models with caching.
"""

from typing import Optional
from pydantic import BaseModel, Field
from enum import Enum
import hashlib


class EmbeddingModel(str, Enum):
    """Supported embedding models."""
    BGE_MULTILINGUAL = "bge-m3"
    E5_MULTILINGUAL = "e5-multilingual"
    MULTILINGUAL_E5_LARGE = "multilingual-e5-large"


class EmbeddingConfig(BaseModel):
    """Configuration for embedding service."""
    
    model: EmbeddingModel = EmbeddingModel.BGE_MULTILINGUAL
    dimension: int = 1024
    max_length: int = 512
    batch_size: int = 32
    normalize: bool = True
    cache_enabled: bool = True
    cache_ttl_seconds: int = 3600


class VectorDocument(BaseModel):
    """Document with embedding for vector search."""
    
    doc_id: str
    content: str
    embedding: list[float]
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)
    source_id: str
    lang: str
    checksum: str
    
    @classmethod
    def compute_checksum(cls, content: str, source_id: str) -> str:
        """Compute SHA-256 checksum for document."""
        data = f"{content}:{source_id}".encode("utf-8")
        return hashlib.sha256(data).hexdigest()


class EmbeddingResult(BaseModel):
    """Result from embedding computation."""
    
    vectors: list[list[float]]
    model: str
    dimensions: int
    normalized: bool
    input_count: int
    
    class Config:
        arbitrary_types_allowed = True


class SemanticCacheEntry(BaseModel):
    """Entry in the semantic cache."""
    
    query_hash: str
    query_text: str
    cached_results: list[str]  # List of doc_ids
    created_at: float
    expires_at: float
    hit_count: int = 0
    
    @property
    def is_expired(self) -> bool:
        """Check if cache entry is expired."""
        import time
        return time.time() > self.expires_at
    
    def record_hit(self) -> None:
        """Record a cache hit."""
        object.__setattr__(self, "hit_count", self.hit_count + 1)
