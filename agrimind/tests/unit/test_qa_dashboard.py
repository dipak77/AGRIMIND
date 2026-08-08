"""QA dashboard / report APIs (offline)."""

from __future__ import annotations

from pathlib import Path

from data_kernel.lakehouse.writer import LakehouseWriter
from data_kernel.pipeline.dedup import DedupIndex
from data_kernel.pipeline.ingest_pipeline import IngestPipeline, IngestRequest
from data_kernel.storage.object_store import LocalObjectStore
from data_ingestion_service.qa import (
    build_dashboard,
    build_report,
    corpus_detail,
    enrich_job,
    quality_detail,
    quarantine_detail,
    stage_progress,
)


def test_stage_progress_percent():
    p = stage_progress({"allow_list": {}, "license": {}, "download": {}}, status="processing")
    assert 0 < p["percent"] < 100
    assert p["completed_count"] == 3
    p2 = stage_progress({"allow_list": {}}, status="curated")
    assert p2["percent"] == 100.0


def test_dashboard_after_ingest(tmp_path: Path, monkeypatch):
    root = tmp_path / "lake"
    tables = root / "tables"
    store = LocalObjectStore(root / "objects")
    writer = LakehouseWriter(store, table_root=tables)
    pipe = IngestPipeline(
        store=store,
        writer=writer,
        dedup=DedupIndex(),
        indexer=None,
        index_on_curate=False,
    )
    # point QA helpers at temp tables
    monkeypatch.setenv("LAKEHOUSE_TABLE_ROOT", str(tables))
    monkeypatch.setenv("OBJECT_STORE", "local")
    monkeypatch.setenv("LAKEHOUSE_ROOT", str(root / "objects"))

    r = pipe.run(
        IngestRequest(
            source_url="https://example.com/qa-dash",
            license="cc-by",
            content=(
                "ICAR cotton crop pest soil health fertilizer irrigation "
                "advisory for farmers IPM practices."
            ),
            skip_robots=True,
        )
    )
    assert r.status == "curated"
    job = {
        "job_id": r.job_id,
        "status": r.status,
        "source_url": "https://example.com/qa-dash",
        "result": {
            "status": r.status,
            "stages": r.stages,
            "manifest_id": r.manifest_id,
            "content_hash": r.content_hash,
        },
    }
    ej = enrich_job(job)
    assert ej["progress"]["percent"] == 100.0
    assert ej["qa_summary"]["quality_score"] is not None

    dash = build_dashboard([job])
    assert dash["kpis"]["curated_documents"] >= 1
    assert dash["corpus"]["total_records"] >= 1
    assert dash["corpus"]["size_bytes"] >= 0

    report = build_report([job], sample_limit=5)
    assert report["qa_score_pct"] >= 0
    assert report["qa_checklist"]

    corp = corpus_detail(limit=10)
    assert corp["summary"]["documents"] >= 1

    q = quality_detail(limit=10)
    assert q["count"] >= 1


def test_quarantine_detail_empty_ok(tmp_path: Path, monkeypatch):
    root = tmp_path / "lake2"
    monkeypatch.setenv("LAKEHOUSE_TABLE_ROOT", str(root / "tables"))
    monkeypatch.setenv("OBJECT_STORE", "local")
    monkeypatch.setenv("LAKEHOUSE_ROOT", str(root / "objects"))
    q = quarantine_detail(limit=5)
    assert q["count"] == 0
