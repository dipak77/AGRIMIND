from memory.retrieval.service import HybridRetriever, RetrievalMode, RetrievalRequest
from memory.vector.embedder import LocalHashEmbedder
from memory.vector.seed_corpus import default_seed_documents
from tests.unit.test_qdrant_retrieval import FakeQdrantStore


def test_hybrid_retrieve_has_citations():
    r = HybridRetriever(backend="stub")
    res = r.retrieve(RetrievalRequest(query="cotton bollworm", lang="en", mode=RetrievalMode.HYBRID))
    assert res.chunks
    assert res.confidence < 0.95  # stub must not fake chemical-dosage threshold
    assert res.chunks[0].citation is not None or res.chunks[0].source_id


def test_modes_exist():
    assert {m.value for m in RetrievalMode} >= {"graph", "vector", "hybrid", "api", "auto"}


def test_live_path_ranks_seed_corpus():
    emb = LocalHashEmbedder(dimension=64)
    store = FakeQdrantStore(dimension=64)
    r = HybridRetriever(backend="live", store=store, embedder=emb)  # type: ignore[arg-type]
    r.upsert_documents(default_seed_documents())
    res = r.retrieve(RetrievalRequest(query="crop rotation soil health", top_k=2))
    assert res.trace and res.trace.backend == "live"
    assert any("rotation" in (c.text or "").lower() for c in res.chunks)
