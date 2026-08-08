"""Qdrant vector store client for AGRIMIND memory plane."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class VectorPoint:
    id: str
    vector: list[float]
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScoredPoint:
    id: str
    score: float
    payload: dict[str, Any]


class QdrantStore:
    """
    Thin wrapper over qdrant-client.

    If qdrant-client is missing or server unreachable, methods raise RuntimeError
    so HybridRetriever can fall back to stub when configured as auto.
    """

    def __init__(
        self,
        url: str = "http://localhost:6333",
        collection: str = "agrimind_chunks",
        dimension: int = 384,
        api_key: str | None = None,
    ) -> None:
        self.url = url.rstrip("/")
        self.collection = collection
        self.dimension = dimension
        self.api_key = api_key
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from qdrant_client import QdrantClient
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "qdrant-client is not installed; add dependency or use backend=stub"
            ) from exc
        kwargs: dict[str, Any] = {"url": self.url, "timeout": 5}
        if self.api_key:
            kwargs["api_key"] = self.api_key
        self._client = QdrantClient(**kwargs)
        return self._client

    def ping(self) -> bool:
        try:
            client = self._get_client()
            client.get_collections()
            return True
        except Exception as exc:
            logger.warning("qdrant_ping_failed", extra={"error": str(exc)})
            return False

    def ensure_collection(self) -> None:
        from qdrant_client.http import models as qm

        client = self._get_client()
        names = {c.name for c in client.get_collections().collections}
        if self.collection in names:
            return
        client.create_collection(
            collection_name=self.collection,
            vectors_config=qm.VectorParams(
                size=self.dimension,
                distance=qm.Distance.COSINE,
            ),
        )
        logger.info("qdrant_collection_created", extra={"collection": self.collection})

    def upsert(self, points: list[VectorPoint]) -> int:
        from qdrant_client.http import models as qm

        if not points:
            return 0
        self.ensure_collection()
        client = self._get_client()
        client.upsert(
            collection_name=self.collection,
            points=[
                qm.PointStruct(
                    id=self._to_point_id(p.id),
                    vector=p.vector,
                    payload={**p.payload, "point_key": p.id},
                )
                for p in points
            ],
            wait=True,
        )
        return len(points)

    def search(
        self,
        vector: list[float],
        top_k: int = 8,
        score_threshold: float | None = 0.15,
        filters: dict[str, Any] | None = None,
    ) -> list[ScoredPoint]:
        from qdrant_client.http import models as qm

        self.ensure_collection()
        client = self._get_client()
        qfilter = None
        if filters:
            must = []
            for k, v in filters.items():
                must.append(
                    qm.FieldCondition(key=k, match=qm.MatchValue(value=v))
                )
            if must:
                qfilter = qm.Filter(must=must)

        # qdrant-client API: query_points (newer) or search (older)
        try:
            hits = client.search(
                collection_name=self.collection,
                query_vector=vector,
                limit=top_k,
                query_filter=qfilter,
                score_threshold=score_threshold,
                with_payload=True,
            )
        except TypeError:
            # older/newer signature drift
            hits = client.search(
                collection_name=self.collection,
                query_vector=vector,
                limit=top_k,
                query_filter=qfilter,
                with_payload=True,
            )

        results: list[ScoredPoint] = []
        for h in hits:
            payload = dict(h.payload or {})
            results.append(
                ScoredPoint(
                    id=str(payload.get("point_key") or h.id),
                    score=float(h.score or 0.0),
                    payload=payload,
                )
            )
        return results

    def count(self) -> int:
        client = self._get_client()
        try:
            info = client.get_collection(self.collection)
            return int(info.points_count or 0)
        except Exception:
            return 0

    @staticmethod
    def _to_point_id(key: str) -> str:
        """Qdrant accepts UUID or unsigned int; use stable UUID5 from key."""
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"agrimind:{key}"))
