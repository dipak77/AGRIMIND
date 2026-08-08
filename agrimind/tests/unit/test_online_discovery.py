"""Agri keyword online discovery (mocked HTTP)."""

from __future__ import annotations

import json
from typing import Any

from data_kernel.sources.agri_taxonomy import (
    keywords_for_categories,
    list_categories,
    match_categories,
)
from data_kernel.sources.online_discovery import (
    DISCOVERY_SERVICES,
    OnlineHit,
    check_access,
    discover_online,
    list_discovery_services,
)


def test_taxonomy_categories_cover_farmer_domain():
    cats = list_categories()
    ids = {c["id"] for c in cats}
    assert "crops" in ids
    assert "soil_health" in ids
    assert "pests_ipm" in ids
    assert "farmer_livelihood" in ids
    assert "agri_books_reference" in ids
    kws = keywords_for_categories(["soil_health", "irrigation_water"])
    assert any("soil" in k for k in kws)
    assert any("irrigation" in k for k in kws)
    assert "soil_health" in match_categories("Soil health and organic carbon")


def test_discovery_services_registry():
    services = list_discovery_services()
    assert len(services) >= 5
    ids = {s["id"] for s in services}
    assert "wikipedia_search" in ids
    assert "open_library" in ids
    assert "internet_archive" in ids
    assert "fao_open" in ids


def test_discover_online_mocked(monkeypatch):
    def fake_search(service_id: str, query: str, *, limit: int, lang: str) -> list[OnlineHit]:
        if service_id == "wikipedia_search":
            return [
                OnlineHit(
                    source_url="https://en.wikipedia.org/wiki/Soil_health",
                    source_type="wikipedia",
                    title="Soil health",
                    provider="Wikipedia",
                    service="wikipedia_search",
                    license="cc-by-sa",
                    snippet="Soil health for farming",
                    score=5.0,
                )
            ]
        if service_id == "open_library":
            return [
                OnlineHit(
                    source_url="https://archive.org/download/farmbook/farmbook.pdf",
                    source_type="pdf",
                    title="Farm book PDF",
                    provider="Open Library",
                    service="open_library",
                    license="mixed_public_domain",
                    score=3.0,
                )
            ]
        return []

    def fake_access(url: str, *, timeout: float = 6.0) -> Any:
        from data_kernel.sources.online_discovery import AccessCheck

        return AccessCheck(
            url=url,
            reachable=True,
            status_code=200,
            content_type="application/pdf" if url.endswith(".pdf") else "text/html",
            is_pdf=url.endswith(".pdf"),
            method="HEAD",
        )

    import data_kernel.sources.online_discovery as od

    monkeypatch.setattr(od, "_search_one", fake_search)
    monkeypatch.setattr(od, "check_access", fake_access)

    res = discover_online(
        query="soil health",
        categories=["soil_health"],
        max_keywords=2,
        per_keyword_limit=2,
        check_access_flag=True,
        max_access_checks=5,
        workers=2,
    )
    assert res["count"] >= 1
    assert res["allowed_count"] >= 1
    urls = {s["source_url"] for s in res["sources"]}
    assert "https://en.wikipedia.org/wiki/Soil_health" in urls
    assert any(s.get("access", {}).get("reachable") for s in res["sources"] if s.get("allowed"))
    assert res["ingest_ready"]


def test_check_access_handles_failure(monkeypatch):
    import urllib.error

    import data_kernel.sources.online_discovery as od

    def boom(*_a: Any, **_k: Any):
        raise urllib.error.URLError("refused")

    monkeypatch.setattr(od.urllib.request, "urlopen", boom)
    ac = check_access("https://en.wikipedia.org/wiki/Agriculture", timeout=1.0)
    assert ac.reachable is False
    assert ac.error


def test_services_json_serializable():
    # ensure registry is plain JSON-friendly for API
    json.dumps(DISCOVERY_SERVICES)
