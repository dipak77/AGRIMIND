"""B1 tests: local embedder + live HybridRetriever with in-memory fake Qdrant."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from memory.retrieval.service import HybridRetriever, RetrievalMode, RetrievalRequest
from memory.vector.embedder import LocalHashEmbedder, cosine_similarity
from memory.vector.qdrant_store import ScoredPoint, VectorPoint
from memory.vector.seed_corpus import default_seed_documents


@dataclass
class FakeQdrantStore:
    """Minimal in-memory stand-in for QdrantStore (unit tests, no server)."""

    url: str = "fake://qdrant"
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


def test_local_hash_embedder_normalized():
    emb = LocalHashEmbedder(dimension=64)
    v = emb.embed("cotton bollworm IPM")
    assert len(v) == 64
    norm = sum(x * x for x in v) ** 0.5
    assert abs(norm - 1.0) < 1e-5


def test_similar_queries_have_higher_similarity():
    emb = LocalHashEmbedder(dimension=128)
    a = emb.embed("cotton bollworm pest treatment IPM")
    b = emb.embed("bollworm on cotton crop IPM practices")
    c = emb.embed("stock market trading stocks")
    assert cosine_similarity(a, b) > cosine_similarity(a, c)


def test_live_retrieve_with_fake_qdrant():
    emb = LocalHashEmbedder(dimension=64)
    store = FakeQdrantStore(dimension=64)
    retriever = HybridRetriever(backend="live", store=store, embedder=emb)  # type: ignore[arg-type]
    n = retriever.upsert_documents(default_seed_documents())
    assert n == len(default_seed_documents())

    res = retriever.retrieve(
        RetrievalRequest(query="cotton bollworm IPM treatment", lang="en", mode="hybrid", top_k=3)
    )
    assert res.trace is not None
    assert res.trace.backend == "live"
    assert res.chunks
    assert res.chunks[0].score >= res.chunks[-1].score
    assert res.confidence < 0.95
    assert res.has_citations
    # best hit should relate to cotton/IPM seed
    top_text = (res.chunks[0].text or "").lower()
    assert "cotton" in top_text or "bollworm" in top_text or "ipm" in top_text


def test_live_empty_index_raises():
    from memory.graph.neo4j_store import InMemoryGraphStore

    emb = LocalHashEmbedder(dimension=32)
    store = FakeQdrantStore(dimension=32)
    empty_graph = InMemoryGraphStore()  # no seed → no paths
    retriever = HybridRetriever(
        backend="live",
        store=store,  # type: ignore[arg-type]
        embedder=emb,
        graph_store=empty_graph,
        vector_enabled=True,
        graph_enabled=True,
    )
    with pytest.raises(RuntimeError, match="no vector hits and no graph paths"):
        retriever.retrieve(RetrievalRequest(query="anything", top_k=3))


def test_auto_falls_back_to_stub_on_live_failure():
    from memory.graph.neo4j_store import InMemoryGraphStore

    class BoomStore(FakeQdrantStore):
        def search(self, *args, **kwargs):
            raise RuntimeError("qdrant down")

    class BoomGraph(InMemoryGraphStore):
        def multi_hop_paths(self, query: str, top_k: int = 5):
            raise RuntimeError("neo4j down")

    retriever = HybridRetriever(
        backend="auto",
        store=BoomStore(),  # type: ignore[arg-type]
        embedder=LocalHashEmbedder(dimension=32),
        graph_store=BoomGraph(),
        vector_enabled=True,
        graph_enabled=True,
    )
    res = retriever.retrieve(RetrievalRequest(query="crop rotation", top_k=3))
    assert res.chunks
    assert res.trace is not None
    assert res.trace.backend in ("stub_fallback", "stub")


def test_stub_backend_unchanged():
    r = HybridRetriever(backend="stub")
    res = r.retrieve(RetrievalRequest(query="soil health", mode=RetrievalMode.HYBRID))
    assert res.trace and res.trace.backend == "stub"
    assert res.confidence < 0.95
