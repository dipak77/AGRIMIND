"""B3 tests: semantic cache (in-memory) + HybridRetriever cache hits. No live Redis."""

from __future__ import annotations

from memory.retrieval.semantic_cache import (
    InMemorySemanticCache,
    build_semantic_cache,
    compact_retrieval_payload,
    normalize_query,
    query_key_hash,
)
from memory.retrieval.service import HybridRetriever, RetrievalMode, RetrievalRequest
from memory.vector.embedder import LocalHashEmbedder, cosine_similarity


def _sample_payload(query: str = "cotton bollworm IPM") -> dict:
    return compact_retrieval_payload(
        {
            "query": query,
            "confidence": 0.85,
            "has_citations": True,
            "chunks": [
                {
                    "chunk_id": "c1",
                    "text": "Use IPM for cotton bollworm; avoid banned chemicals.",
                    "content": "Use IPM for cotton bollworm; avoid banned chemicals.",
                    "score": 0.9,
                    "source_id": "src_icar_001",
                    "source_type": "document",
                    "url_or_path": "s3://agrimind/icar.pdf",
                    "checksum": "sha256:abc",
                    "lang": "en",
                    "metadata": {"backend": "stub"},
                    "citation": None,
                }
            ],
            "graph_paths": [
                {
                    "path_id": "p1",
                    "summary": "Cotton -[AFFECTED_BY]-> Bollworm -[MANAGED_BY]-> IPM",
                    "confidence": 0.8,
                    "is_approved": True,
                    "nodes": [{"id": "crop:cotton", "name": "Cotton"}],
                    "relationships": [],
                    "citations": [{"source_id": "src_icar_001"}],
                }
            ],
            "trace": {
                "backend": "stub",
                "mode": "hybrid",
                "graph_results_count": 1,
                "vector_results_count": 1,
                "embedder": "agrimind-local-hash-v1",
                "graph_backend": "in_memory",
            },
        }
    )


def test_normalize_and_hash_stable():
    assert normalize_query("  Cotton   Bollworm  ") == "cotton bollworm"
    h1 = query_key_hash("Cotton Bollworm", "en")
    h2 = query_key_hash("  cotton   bollworm ", "EN")
    assert h1 == h2


def test_exact_cache_hit():
    cache = InMemorySemanticCache(threshold=0.92, default_ttl=3600)
    payload = _sample_payload()
    cache.set("cotton bollworm IPM", "en", payload)
    hit = cache.get("cotton bollworm IPM", "en")
    assert hit is not None
    assert hit["confidence"] == 0.85
    assert hit["chunks"]
    assert cache.hits == 1
    assert cache.misses == 0


def test_semantic_near_hit():
    """Near-paraphrase hits when cosine ≥ threshold (threshold adapted to embedder)."""
    emb = LocalHashEmbedder(dimension=128)
    q1 = "cotton bollworm pest treatment IPM"
    q2 = "bollworm on cotton crop IPM practices"
    q_unrelated = "stock market trading shares"
    sim = cosine_similarity(emb.embed(q1), emb.embed(q2))
    sim_bad = cosine_similarity(emb.embed(q1), emb.embed(q_unrelated))
    assert sim > sim_bad
    # threshold between near and unrelated so only paraphrase hits
    thr = (sim + sim_bad) / 2.0
    cache = InMemorySemanticCache(threshold=thr, default_ttl=3600, embedder=emb)
    cache.set(q1, "en", _sample_payload(q1))
    hit = cache.get(q2, "en")
    assert hit is not None
    assert cache.hits >= 1
    assert hit["confidence"] == 0.85
    assert cache.get(q_unrelated, "en") is None


def test_cache_miss_unrelated():
    emb = LocalHashEmbedder(dimension=128)
    cache = InMemorySemanticCache(threshold=0.92, default_ttl=3600, embedder=emb)
    cache.set("cotton bollworm IPM", "en", _sample_payload())
    miss = cache.get("stock market trading shares", "en")
    assert miss is None
    assert cache.misses >= 1


def test_lang_isolation():
    cache = InMemorySemanticCache()
    cache.set("bollworm", "en", _sample_payload())
    assert cache.get("bollworm", "hi") is None


def test_build_semantic_cache_disabled_returns_none():
    assert build_semantic_cache(enabled=False) is None


def test_build_semantic_cache_falls_back_memory():
    # unreachable / bogus redis → in-memory
    cache = build_semantic_cache(
        "redis://127.0.0.1:1/0",
        enabled=True,
        threshold=0.9,
        ttl=60,
    )
    assert cache is not None
    assert cache.backend_name == "memory"
    cache.set("q", "en", _sample_payload())
    assert cache.get("q", "en") is not None


def test_hybrid_retriever_second_call_is_cache_hit():
    cache = InMemorySemanticCache(threshold=0.92, default_ttl=3600)
    r = HybridRetriever(
        backend="stub",
        semantic_cache=cache,
        cache_enabled=True,
    )
    req = RetrievalRequest(query="bollworm on cotton IPM", lang="en", mode=RetrievalMode.HYBRID)
    first = r.retrieve(req)
    assert first.trace is not None
    assert first.trace.cache_hit is False
    assert first.chunks or first.graph_paths

    second = r.retrieve(
        RetrievalRequest(query="bollworm on cotton IPM", lang="en", mode=RetrievalMode.HYBRID)
    )
    assert second.trace is not None
    assert second.trace.cache_hit is True
    assert second.trace.backend == "cache"
    assert second.confidence == first.confidence
    assert cache.hits >= 1


def test_disabled_cache_never_hits():
    cache = InMemorySemanticCache()
    r = HybridRetriever(
        backend="stub",
        semantic_cache=cache,
        cache_enabled=False,
    )
    req = RetrievalRequest(query="cotton pest IPM", lang="en")
    a = r.retrieve(req)
    b = r.retrieve(req)
    assert a.trace and a.trace.cache_hit is False
    assert b.trace and b.trace.cache_hit is False
    assert cache.size() == 0
    assert r.cache_stats()["enabled"] is False


def test_no_cache_instance_never_hits():
    r = HybridRetriever(backend="stub")
    req = RetrievalRequest(query="cotton bollworm", lang="en")
    a = r.retrieve(req)
    b = r.retrieve(req)
    assert a.trace and a.trace.cache_hit is False
    assert b.trace and b.trace.cache_hit is False
    assert r.cache_stats()["backend"] == "none"


def test_cache_stats_shape():
    cache = InMemorySemanticCache()
    cache.set("x", "en", _sample_payload())
    cache.get("x", "en")
    cache.get("totally different query xyz", "en")
    stats = cache.stats()
    assert stats["backend"] == "memory"
    assert stats["hits"] >= 1
    assert stats["misses"] >= 1
    assert stats["size"] >= 1
