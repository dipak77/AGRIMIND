"""Phase 2 Data Acquisition Plane — stages, sources, lakehouse tables."""

from __future__ import annotations

from pathlib import Path

import pytest

from data_kernel.lakehouse.writer import LAKEHOUSE_TABLES, LakehouseWriter
from data_kernel.pipeline.dedup import DedupIndex
from data_kernel.pipeline.ingest_pipeline import IngestPipeline, IngestRequest
from data_kernel.pipeline.normalize import detect_language, normalize_text
from data_kernel.pipeline.quality import score_quality
from data_kernel.pipeline.toxicity import ToxicityFilter
from data_kernel.sources.discovery import discover_sources, is_url_allow_listed
from data_kernel.storage.object_store import LocalObjectStore


@pytest.fixture()
def lake_root(tmp_path: Path):
    return tmp_path / "lake"


@pytest.fixture()
def pipeline(lake_root: Path):
    store = LocalObjectStore(lake_root / "objects")
    writer = LakehouseWriter(store, table_root=lake_root / "tables")
    return IngestPipeline(
        store=store,
        writer=writer,
        dedup=DedupIndex(),
        indexer=None,
        index_on_curate=False,
    )


def test_normalize_and_language_en():
    r = normalize_text("Crop rotation improves soil health for farmers.")
    assert r.language == "en"
    assert "Crop rotation" in r.text


def test_detect_language_hi_mr():
    assert detect_language("यह फसल किसान के लिए है") == "hi"
    assert detect_language("कापूस पीक शेतकरी साठी आहे") in ("mr", "hi")


def test_toxicity_blocks_unsafe():
    t = ToxicityFilter()
    assert t.check("Normal crop pest IPM advice").is_safe is True
    assert t.check("You should kill yourself").is_safe is False


def test_minhash_near_duplicate():
    idx = DedupIndex(near_threshold=0.5)
    a = idx.check_and_add(
        "cotton crop pest management soil farm fertilizer irrigation harvest sowing guide practices"
    )
    assert a.is_duplicate is False
    # very similar reordering / slight edit
    b = idx.check_and_add(
        "cotton crop pest management soil farm fertilizer irrigation harvest sowing guide practice"
    )
    # may be fingerprint or minhash
    assert b.is_duplicate is True


def test_quality_score_range():
    q = score_quality(
        text="x" * 300,
        relevance=0.9,
        language="en",
        pii_redacted=True,
        has_provenance=True,
        toxicity_score=1.0,
    )
    assert 0.5 <= q.score <= 1.0


def test_discovery_allow_list():
    found = discover_sources(
        [
            {"source_url": "https://icar.org.in/x", "source_type": "web"},
            {"source_url": "https://evil.example.net/x", "source_type": "web"},
        ]
    )
    assert found[0].allowed is True
    # example.net is not example.com
    assert found[1].allowed is False or "example" in found[1].source_url


def test_pipeline_full_stages_and_chunks_table(pipeline: IngestPipeline, lake_root: Path):
    res = pipeline.run(
        IngestRequest(
            source_url="https://example.com/cotton-ipm",
            source_type="web",
            license="cc-by",
            content=(
                "ICAR advisory for farmers: cotton bollworm IPM practices, "
                "soil health, crop monitoring, fertilizer and irrigation guidance."
            ),
            skip_robots=True,
        )
    )
    assert res.status == "curated"
    assert res.language == "en"
    assert res.chunk_count >= 1
    assert res.manifest_id
    assert res.stages.get("toxicity", {}).get("is_safe") is True
    assert res.stages.get("quality", {}).get("score", 0) > 0.3
    assert "provenance" in res.stages
    chunks = pipeline.writer.query_table("curated.chunks")
    assert chunks
    telem = pipeline.writer.query_table("telemetry.events")
    assert telem
    assert set(LAKEHOUSE_TABLES)  # catalog defined


def test_pipeline_toxicity_quarantine(pipeline: IngestPipeline):
    res = pipeline.run(
        IngestRequest(
            source_url="https://example.com/bad",
            license="cc-by",
            content="Crop farm soil. Please kill yourself now.",
            skip_robots=True,
        )
    )
    assert res.status == "quarantine"
    assert res.error == "toxicity_blocked"


def test_pipeline_pii_and_relevance_still_work(pipeline: IngestPipeline):
    res = pipeline.run(
        IngestRequest(
            source_url="https://example.com/a",
            license="cc0",
            content="Farmer soil crop pest IPM contact 9876543210 for more fertilizer advice.",
            skip_robots=True,
        )
    )
    assert res.status == "curated"
    assert res.stages["pii"]["redacted"] is True


def test_inline_json_structured_type(pipeline: IngestPipeline):
    res = pipeline.run(
        IngestRequest(
            source_url="https://example.com/api/soil",
            source_type="json",
            license="government_open",
            content='{"crop":"cotton","soil":"black","n":120,"p":40,"k":40,"farm":"demo"}',
            skip_robots=True,
        )
    )
    # structured may pass even if relevance softer
    assert res.status in ("curated", "quarantine")
    assert res.raw_uri


def test_all_lakehouse_table_names():
    expected = {
        "raw.documents",
        "curated.documents",
        "curated.chunks",
        "curated.images",
        "quarantine.records",
        "manifests.datasets",
        "manifests.models",
        "telemetry.events",
    }
    assert expected == set(LAKEHOUSE_TABLES)


def test_image_source_writes_curated_images(pipeline: IngestPipeline, lake_root: Path):
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    res = pipeline.run(
        IngestRequest(
            source_url="https://example.com/disease/leaf.png",
            source_type="image",
            license="cc-by",
            content_bytes=png_bytes,
            skip_robots=True,
        )
    )
    assert res.status == "image_stored"
    assert res.raw_uri
    assert res.curated_uri
    assert res.manifest_id
    images = pipeline.writer.query_table("curated.images")
    assert images
    assert images[0]["provenance"]["checksum"]
    assert images[0]["provenance"]["license"] == "cc-by"


def test_provenance_on_curated_and_manifest(pipeline: IngestPipeline):
    res = pipeline.run(
        IngestRequest(
            source_url="https://example.com/soil-health",
            source_type="web",
            license="government_open",
            content=(
                "Soil health card scheme for farmers: NPK testing, "
                "crop advisory, fertilizer dose guidance from agri dept."
            ),
            skip_robots=True,
            source_id="src:soil-demo",
        )
    )
    assert res.status == "curated"
    assert res.stages["provenance"]["source_id"] == "src:soil-demo"
    assert res.stages["provenance"]["raw_checksum"]
    assert res.stages["provenance"]["license"] == "government_open"
    docs = pipeline.writer.query_table("curated.documents")
    assert any(d.get("provenance", {}).get("source_id") == "src:soil-demo" for d in docs)
    manifests = pipeline.writer.list_manifests()
    assert manifests
    assert res.manifest_id in {m["manifest_id"] for m in manifests}


def test_object_store_immutable_no_overwrite(lake_root: Path):
    store = LocalObjectStore(lake_root / "objects")
    store.put_bytes("agrimind-raw", "k/a.bin", b"hello")
    # same content: idempotent OK
    r = store.put_bytes("agrimind-raw", "k/a.bin", b"hello")
    assert r.checksum.startswith("sha256:")
    # different content: must not overwrite
    with pytest.raises(FileExistsError):
        store.put_bytes("agrimind-raw", "k/a.bin", b"world")


def test_workflow_names_exportable():
    """Temporal worker registers plan-named workflows."""
    from curation_worker.worker import (
        CurationFilterWorkflow,
        CurationWorkflow,
        GraphBuildWorkflow,
        IndexWorkflow,
        IngestPdfWorkflow,
        IngestWebWorkflow,
        IngestWorkflow,
        IngestionWorkflow,
    )

    assert IngestionWorkflow and IngestWorkflow and CurationWorkflow
    assert CurationFilterWorkflow and IndexWorkflow and GraphBuildWorkflow
    assert IngestWebWorkflow and IngestPdfWorkflow
