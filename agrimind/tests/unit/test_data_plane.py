"""Phase C tests: ingest pipeline, filters, lakehouse (offline local store)."""

from __future__ import annotations

from pathlib import Path

import pytest

from data_kernel.lakehouse.writer import LakehouseWriter
from data_kernel.pipeline.dedup import DedupIndex
from data_kernel.pipeline.ingest_pipeline import IngestPipeline, IngestRequest
from data_kernel.pipeline.license_filter import LicenseFilter
from data_kernel.pipeline.pii import PIIFilter
from data_kernel.pipeline.relevance import AgricultureRelevanceFilter
from data_kernel.storage.object_store import LocalObjectStore


@pytest.fixture()
def lake_root(tmp_path: Path):
    return tmp_path / "lake"


@pytest.fixture()
def pipeline(lake_root: Path):
    store = LocalObjectStore(lake_root / "objects")
    writer = LakehouseWriter(store, table_root=lake_root / "tables")
    return IngestPipeline(store=store, writer=writer, dedup=DedupIndex())


def test_pii_redacts_phone_and_aadhaar():
    r = PIIFilter().redact("Call 9876543210 aadhaar 1234 5678 9012")
    assert "[REDACTED_PHONE]" in r.text
    assert "[REDACTED_ID]" in r.text
    assert r.redacted


def test_relevance_agri_vs_noise():
    f = AgricultureRelevanceFilter()
    good = f.score("Cotton crop pest IPM fertilizer soil health for farmers")
    bad = f.score("Stock market crypto trading tips")
    assert good.relevant is True
    assert bad.relevant is False


def test_license_blocks_restricted():
    f = LicenseFilter()
    assert f.check("cc-by").allowed is True
    assert f.check("restricted").allowed is False


def test_dedup_exact_and_near():
    idx = DedupIndex()
    a = idx.check_and_add("cotton crop pest management soil farm")
    assert a.is_duplicate is False
    b = idx.check_and_add("cotton crop pest management soil farm")
    assert b.is_duplicate is True
    assert b.reason == "exact_hash"


def test_pipeline_curates_inline_agri_content(pipeline: IngestPipeline):
    res = pipeline.run(
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
    assert res.raw_uri
    assert res.curated_uri
    assert res.manifest_id
    assert res.content_hash
    assert res.stages["raw_write"]["backend"] == "local_fs"
    assert res.stages["relevance"]["relevant"] is True
    # no indexer attached by default fixture → index stage skipped
    assert res.stages.get("index", {}).get("skipped") is True


def test_pipeline_with_recording_indexer_indexes_chunks(lake_root: Path):
    from data_kernel.pipeline.indexer import RecordingChunkIndexer

    store = LocalObjectStore(lake_root / "objects")
    writer = LakehouseWriter(store, table_root=lake_root / "tables")
    rec = RecordingChunkIndexer()
    pipe = IngestPipeline(
        store=store,
        writer=writer,
        dedup=DedupIndex(),
        indexer=rec,
        index_on_curate=True,
    )
    res = pipe.run(
        IngestRequest(
            source_url="https://example.com/wheat-rust",
            license="cc-by",
            content=(
                "Wheat crop disease rust management for farmers: "
                "resistant varieties, field scouting, and approved fungicides only."
            ),
        )
    )
    assert res.status == "curated"
    assert res.stages["index"]["upserted"] >= 1
    assert rec.all_docs
    assert any("wheat" in d["text"].lower() for d in rec.all_docs)
    assert rec.all_docs[0].get("document_id")


def test_pipeline_quarantine_low_relevance(pipeline: IngestPipeline):
    res = pipeline.run(
        IngestRequest(
            source_url="https://example.com/crypto",
            license="cc-by",
            content="Buy bitcoin and ethereum for stock market profits.",
        )
    )
    assert res.status == "quarantine"
    assert res.quarantine_uri
    assert res.error == "low_agriculture_relevance"


def test_pipeline_quarantine_duplicate(pipeline: IngestPipeline):
    text = "Farm soil crop pest fertilizer irrigation harvest sowing guide."
    r1 = pipeline.run(
        IngestRequest(source_url="https://example.com/a", license="cc0", content=text)
    )
    r2 = pipeline.run(
        IngestRequest(source_url="https://example.com/b", license="cc0", content=text)
    )
    assert r1.status == "curated"
    assert r2.status == "quarantine"
    assert "duplicate" in (r2.error or "")


def test_pipeline_quarantine_not_allow_listed(pipeline: IngestPipeline):
    res = pipeline.run(
        IngestRequest(
            source_url="https://evil-spam.notallowlisted.test/page",
            license="cc-by",
            content=None,
            allow_list=["icar.org.in", "gov.in", "example.com"],
        )
    )
    assert res.status == "quarantine"
    assert res.error == "source_not_allow_listed"


def test_manifest_queryable(pipeline: IngestPipeline, lake_root: Path):
    pipeline.run(
        IngestRequest(
            source_url="https://example.com/agri",
            license="government_open",
            content="Agriculture crop soil farm pest control IPM practices.",
        )
    )
    manifests = pipeline.writer.list_manifests()
    assert manifests
    assert manifests[-1]["manifest_id"]
    curated = pipeline.writer.query_table("curated.documents")
    assert curated
    assert curated[-1]["status"] == "curated"


def test_local_object_store_checksum(lake_root: Path):
    store = LocalObjectStore(lake_root)
    put = store.put_bytes("test-bucket", "a/b.txt", b"hello-agri")
    assert put.checksum.startswith("sha256:")
    assert store.exists("test-bucket", "a/b.txt")
    assert store.get_bytes("test-bucket", "a/b.txt") == b"hello-agri"


def test_build_object_store_prefer_local(lake_root: Path):
    from data_kernel.storage.object_store import build_object_store, clear_object_store_cache

    clear_object_store_cache()
    store = build_object_store(prefer="local", local_root=str(lake_root))
    assert store.backend == "local_fs"
    assert store.ping() is True


def test_build_object_store_auto_caches_minio_failure(lake_root: Path, monkeypatch):
    """Dashboard polls must not re-probe MinIO every few seconds when it is down."""
    from data_kernel.storage import object_store as os_mod
    from data_kernel.storage.object_store import build_object_store, clear_object_store_cache

    clear_object_store_cache()
    pings = {"n": 0}

    def fake_ping(self):  # noqa: ANN001
        pings["n"] += 1
        return False

    monkeypatch.setattr(os_mod.MinioObjectStore, "ping", fake_ping)

    a = build_object_store(
        prefer="auto",
        local_root=str(lake_root / "a"),
        minio_endpoint="http://127.0.0.1:9",
    )
    b = build_object_store(
        prefer="auto",
        local_root=str(lake_root / "a"),
        minio_endpoint="http://127.0.0.1:9",
    )
    assert a.backend == "local_fs"
    assert b.backend == "local_fs"
    assert pings["n"] == 1  # second call served from cache

    clear_object_store_cache()
    c = build_object_store(
        prefer="auto",
        local_root=str(lake_root / "a"),
        minio_endpoint="http://127.0.0.1:9",
    )
    assert c.backend == "local_fs"
    assert pings["n"] == 2  # re-probe after cache clear
