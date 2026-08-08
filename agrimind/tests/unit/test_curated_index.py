"""Post-curate indexing: chunker + ChunkIndexer → FakeQdrant / LocalHashEmbedder (offline)."""

from __future__ import annotations

from pathlib import Path

import pytest

from data_kernel.lakehouse.writer import LakehouseWriter
from data_kernel.pipeline.chunking import chunk_text, title_from_url
from data_kernel.pipeline.indexer import NoOpChunkIndexer, RecordingChunkIndexer
from data_kernel.pipeline.ingest_pipeline import IngestPipeline, IngestRequest
from data_kernel.storage.object_store import LocalObjectStore
from memory.indexing.curated_indexer import MemoryChunkIndexer, build_default_indexer
from memory.retrieval.service import HybridRetriever, RetrievalRequest
from memory.vector.embedder import LocalHashEmbedder
from tests.unit.test_qdrant_retrieval import FakeQdrantStore


@pytest.fixture()
def lake_root(tmp_path: Path):
    return tmp_path / "lake"


def _pipeline(
    lake_root: Path,
    *,
    indexer=None,
    index_on_curate: bool = True,
    index_required: bool = False,
) -> IngestPipeline:
    store = LocalObjectStore(lake_root / "objects")
    writer = LakehouseWriter(store, table_root=lake_root / "tables")
    return IngestPipeline(
        store=store,
        writer=writer,
        dedup=__import__("data_kernel.pipeline.dedup", fromlist=["DedupIndex"]).DedupIndex(),
        indexer=indexer,
        index_on_curate=index_on_curate,
        index_required=index_required,
    )


def test_chunk_text_paragraphs_and_max_chars():
    text = "Para one about cotton.\n\n" + ("word " * 300)
    chunks = chunk_text(text, source_id="doc1", max_chars=200, overlap=20)
    assert len(chunks) >= 2
    assert chunks[0]["chunk_index"] == 0
    assert chunks[0]["source_id"] == "doc1"
    assert all(len(c["text"]) <= 220 for c in chunks)  # slight slack for packing
    assert all("text" in c for c in chunks)


def test_title_from_url():
    assert "cotton" in title_from_url("https://example.com/cotton-ipm.pdf").lower()


def test_recording_indexer_called_after_curate(lake_root: Path):
    rec = RecordingChunkIndexer()
    pipe = _pipeline(lake_root, indexer=rec)
    res = pipe.run(
        IngestRequest(
            source_url="https://example.com/cotton-ipm",
            license="cc-by",
            content=(
                "ICAR advisory: cotton bollworm IPM for farmers — "
                "monitor fields, pheromone traps, soil and crop health."
            ),
        )
    )
    assert res.status == "curated"
    assert res.stages["index"]["upserted"] >= 1
    assert res.stages["index"]["backend"] == "recording"
    assert rec.calls
    docs = rec.all_docs
    assert any("bollworm" in (d.get("text") or "").lower() for d in docs)
    assert all(d.get("source_url") == "https://example.com/cotton-ipm" for d in docs)
    assert all(d.get("job_id") for d in docs)
    assert all(d.get("checksum") for d in docs)


def test_index_skipped_when_no_indexer(lake_root: Path):
    pipe = _pipeline(lake_root, indexer=None)
    res = pipe.run(
        IngestRequest(
            source_url="https://example.com/soil",
            license="cc0",
            content="Farm soil crop pest fertilizer irrigation harvest sowing guide.",
        )
    )
    assert res.status == "curated"
    assert res.stages["index"]["skipped"] is True


def test_index_failure_does_not_fail_ingest_by_default(lake_root: Path):
    class BoomIndexer:
        backend = "boom"

        def index_chunks(self, docs):
            raise RuntimeError("vector store down")

    pipe = _pipeline(lake_root, indexer=BoomIndexer(), index_required=False)
    res = pipe.run(
        IngestRequest(
            source_url="https://example.com/ipm",
            license="cc-by",
            content="Cotton crop pest IPM fertilizer soil health for farmers advisory.",
        )
    )
    assert res.status == "curated"
    assert res.stages["index"]["error"]
    assert res.stages["index"]["upserted"] == 0


def test_index_required_quarantines_on_failure(lake_root: Path):
    class BoomIndexer:
        backend = "boom"

        def index_chunks(self, docs):
            raise RuntimeError("vector store down")

    pipe = _pipeline(lake_root, indexer=BoomIndexer(), index_required=True)
    res = pipe.run(
        IngestRequest(
            source_url="https://example.com/ipm2",
            license="cc-by",
            content="Cotton crop pest IPM fertilizer soil health for farmers advisory.",
        )
    )
    assert res.status == "quarantine"
    assert "index_failed" in (res.error or "")


def test_full_path_memory_indexer_searchable(lake_root: Path):
    emb = LocalHashEmbedder(dimension=64)
    store = FakeQdrantStore(dimension=64)
    indexer = MemoryChunkIndexer(
        store=store,
        embedder=emb,
        backend_label="fake_qdrant",
    )
    pipe = _pipeline(lake_root, indexer=indexer)
    content = (
        "ICAR cotton bollworm integrated pest management advisory for farmers. "
        "Use pheromone traps, field monitoring, and neem-based products. "
        "Soil health and crop rotation reduce pest pressure on cotton."
    )
    res = pipe.run(
        IngestRequest(
            source_url="https://example.com/cotton-bollworm-ipm",
            license="government_open",
            content=content,
        )
    )
    assert res.status == "curated"
    assert res.stages["index"]["upserted"] >= 1
    assert store.count() >= 1

    retriever = HybridRetriever(
        backend="live",
        store=store,  # type: ignore[arg-type]
        embedder=emb,
        graph_enabled=False,
        vector_enabled=True,
        cache_enabled=False,
    )
    hit = retriever.retrieve(
        RetrievalRequest(
            query="cotton bollworm IPM pheromone traps",
            lang="en",
            mode="vector",
            top_k=3,
        )
    )
    assert hit.chunks
    top = (hit.chunks[0].text or "").lower()
    assert "cotton" in top or "bollworm" in top or "pheromone" in top or "ipm" in top
    # provenance on vector payload
    assert hit.chunks[0].checksum or hit.chunks[0].url_or_path


def test_build_default_indexer_prefer_in_memory():
    idx = build_default_indexer(prefer_in_memory=True, collection="test_chunks")
    assert idx.backend == "in_memory"
    n = idx.index_chunks(
        [
            {
                "doc_id": "t1:chunk:0",
                "text": "rice paddy irrigation schedule for farmers",
                "source_id": "t1",
                "source_url": "https://example.com/rice",
            }
        ]
    )
    assert n == 1


def test_noop_indexer():
    assert NoOpChunkIndexer().index_chunks([{"text": "x"}]) == 0
