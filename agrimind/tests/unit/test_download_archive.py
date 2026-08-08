"""Download helpers: partial PDF + progress honesty for failures."""

from __future__ import annotations

from data_ingestion_service.qa import stage_progress
from data_kernel.pipeline.download import download_bytes


def test_failed_download_progress_not_100():
    stages = {
        "allow_list": {"allowed": True},
        "license": {"allowed": True},
        "robots": {"allowed": True, "skipped": True},
        "download": {"ok": False, "error": "payload_exceeds_size_limit"},
    }
    p = stage_progress(stages, status="failed")
    assert p["percent"] < 100
    assert p["partial"] is True
    assert p["failed_stage"] == "download"
    assert p["current_stage"] == "download"
    assert "download" not in p["completed_stages"]


def test_curated_still_100():
    stages = {s: {"ok": True} for s in (
        "allow_list", "license", "robots", "download", "raw_write",
        "normalize", "pii", "toxicity", "relevance", "dedup", "quality",
        "provenance", "curated_write", "chunks_write", "manifest",
    )}
    p = stage_progress(stages, status="curated")
    assert p["percent"] == 100.0


def test_download_partial_flag(monkeypatch):
    """When allow_partial=True, oversized body is truncated not raised."""
    import data_kernel.pipeline.download as dl

    class FakeResp:
        status = 200
        headers = {"Content-Type": "application/pdf"}

        def read(self, n):
            return b"%PDF" + b"x" * n

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(dl, "resolve_archive_pdf_url", lambda *a, **k: None)
    monkeypatch.setattr(
        dl.urllib.request,
        "urlopen",
        lambda *a, **k: FakeResp(),
    )
    res = download_bytes(
        "https://example.com/big.pdf",
        max_bytes=1000,
        allow_partial=True,
        retries=1,
    )
    assert len(res.data) == 1000
    assert res.meta.get("partial") is True
