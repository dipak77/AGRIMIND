"""B2 tests: multi-hop graph paths with citations; banned chemicals excluded."""

from memory.graph.neo4j_store import InMemoryGraphStore
from memory.graph.seed_graph import default_graph_edges
from memory.retrieval.service import HybridRetriever, RetrievalMode, RetrievalRequest
from memory.vector.embedder import LocalHashEmbedder
from tests.unit.test_qdrant_retrieval import FakeQdrantStore


def test_in_memory_seed_and_multihop_cotton_bollworm():
    g = InMemoryGraphStore()
    seeded = g.seed_default()
    assert seeded["nodes"] >= 5
    paths = g.multi_hop_paths("cotton bollworm IPM", top_k=5)
    assert paths
    summaries = " ".join(p.summary for p in paths).lower()
    assert "cotton" in summaries or "bollworm" in summaries or "ipm" in summaries
    # citations present on paths
    assert any(p.citations for p in paths)
    # banned monocrotophos must not appear as approved treatment path
    for p in paths:
        names = " ".join(str(n.get("name") or "") for n in p.nodes).lower()
        assert "monocrotophos" not in names
        assert p.is_approved is True


def test_hybrid_stub_returns_graph_paths():
    r = HybridRetriever(backend="stub")
    res = r.retrieve(RetrievalRequest(query="bollworm on cotton", mode=RetrievalMode.HYBRID))
    assert res.graph_paths
    assert res.graph_paths[0].summary or res.graph_paths[0].nodes
    assert res.trace and res.trace.graph_results_count >= 1


def test_graph_only_mode():
    r = HybridRetriever(backend="stub")
    res = r.retrieve(RetrievalRequest(query="crop rotation", mode=RetrievalMode.GRAPH, top_k=3))
    assert res.graph_paths or res.chunks
    # graph mode prefers graph-backed chunks
    if res.chunks:
        assert any(
            (c.metadata or {}).get("backend") == "graph" or c.source_type == "knowledge_graph"
            for c in res.chunks
        )


def test_live_hybrid_with_fake_vector_and_memory_graph():
    emb = LocalHashEmbedder(dimension=64)
    store = FakeQdrantStore(dimension=64)
    graph = InMemoryGraphStore()
    graph.seed_default()
    r = HybridRetriever(
        backend="live",
        store=store,  # type: ignore[arg-type]
        embedder=emb,
        graph_store=graph,
        vector_enabled=True,
        graph_enabled=True,
    )
    # seed vectors from graph-related docs
    r.upsert_documents(
        [
            {
                "doc_id": "src_icar_cotton_ipm_001",
                "text": "Cotton bollworm IPM practices neem pheromone traps",
                "source_id": "src_icar_cotton_ipm_001",
                "title": "ICAR",
                "lang": "en",
            }
        ]
    )
    res = r.retrieve(RetrievalRequest(query="cotton bollworm treatment", mode="hybrid", top_k=5))
    assert res.trace and res.trace.backend == "live"
    assert res.graph_paths
    assert res.chunks
    assert res.confidence < 0.95


def test_default_seed_has_provenance_edges():
    edges = default_graph_edges()
    assert any(e.get("source_id") for e in edges)
    approved = [e for e in edges if e.get("is_approved")]
    banned = [e for e in edges if e.get("banned")]
    assert approved
    assert banned  # present in data but filtered at query time
