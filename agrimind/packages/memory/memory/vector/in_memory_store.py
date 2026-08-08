"""In-memory vector store (offline / tests / Qdrant fallback)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from memory.vector.embedder import cosine_similarity
from memory.vector.qdrant_store import ScoredPoint, VectorPoint


@dataclass
class InMemoryVectorStore:
    """Minimal stand-in for QdrantStore — no server required."""

    url: str = "memory://local"
    collection: str = "agrimind_chunks"
    dimension: int = 384
    points: dict[str, VectorPoint] = field(default_factory=dict)

    def ping(self) -> bool:
        return True

    def ensure_collection(self) -> None:
        return None

    def upsert(self, points: list[VectorPoint]) -> int:
        for p in points:
            self.points[p.id] = p
        return len(points)

    def search(
        self,
        vector: list[float],
        top_k: int = 8,
        score_threshold: float | None = 0.0,
        filters: dict[str, Any] | None = None,
    ) -> list[ScoredPoint]:
        scored: list[ScoredPoint] = []
        for p in self.points.values():
            if filters:
                if any(p.payload.get(k) != v for k, v in filters.items()):
                    continue
            score = cosine_similarity(vector, p.vector)
            if score_threshold is not None and score < score_threshold:
                continue
            scored.append(ScoredPoint(id=p.id, score=score, payload=dict(p.payload)))
        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]

    def count(self) -> int:
        return len(self.points)
