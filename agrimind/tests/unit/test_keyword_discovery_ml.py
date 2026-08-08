"""Multilingual keyword discovery + improved discovery plan."""

from __future__ import annotations

from data_kernel.sources.discovery import (
    DEFAULT_ALLOW_LIST,
    default_seed_catalog,
    discover_sources,
    infer_license,
    infer_trust_score,
    is_url_allow_listed,
    normalize_license,
)
from data_kernel.sources.keyword_discovery_service import (
    expand_keywords,
    AutoSourceDiscoveryService,
)


def test_allow_list_expanded_for_agri_research():
    assert is_url_allow_listed("https://www.irri.org/crop-knowledge")
    assert is_url_allow_listed("https://www.icrisat.org/crops/")
    assert is_url_allow_listed("https://data.gov.in/catalogs")
    assert is_url_allow_listed("https://hi.wikipedia.org/wiki/कृषि")
    assert is_url_allow_listed("https://mr.wikipedia.org/wiki/शेती")
    assert not is_url_allow_listed("https://evil.example.net/x")
    assert len(DEFAULT_ALLOW_LIST) >= 40


def test_license_normalize_and_trust():
    assert normalize_license("cc-by-sa-4.0") == "cc-by-sa"
    assert normalize_license("godl-india") == "government_open"
    assert normalize_license("public-domain") == "cc0"
    assert infer_license("https://www.fao.org/x.pdf") == "cc-by"
    assert infer_trust_score("https://icar.org.in/") >= 90


def test_seed_catalog_has_en_hi_mr():
    seed = default_seed_catalog()
    langs = {s.get("language") for s in seed}
    assert "en" in langs
    assert "hi" in langs
    assert "mr" in langs
    assert any(s.get("source_type") == "pdf" for s in seed)
    assert len(seed) >= 20


def test_expand_keywords_en_hi_mr():
    exp = expand_keywords(["cotton", "soil health"], ["en", "hi", "mr"])
    assert any("cotton" in k.lower() for k in exp["en"])
    assert any("कपास" in k for k in exp["hi"])
    assert any("कापूस" in k for k in exp["mr"])
    assert any("soil" in k.lower() for k in exp["en"])
    assert exp["hi"]  # Devanagari soil terms
    assert exp["mr"]


def test_discover_sources_enriches_fields():
    found = discover_sources(
        [
            {
                "source_url": "https://en.wikipedia.org/wiki/Soil_health",
                "source_type": "wikipedia",
                "title": "Soil health",
                "language": "en",
            },
            {"source_url": "https://evil.example.net/x", "source_type": "web"},
        ]
    )
    assert found[0].allowed is True
    assert found[0].provider == "Wikipedia"
    assert found[0].trust_score >= 70
    assert found[1].allowed is False


def test_auto_discovery_offline_seed_only(monkeypatch):
    """Without network, seed catalog still returns HI/MR/EN agri sources."""
    import data_kernel.sources.keyword_discovery_service as kds

    monkeypatch.setattr(kds.WikipediaSearch, "search", staticmethod(lambda *a, **k: []))
    monkeypatch.setattr(kds.ArchiveOrgSearch, "search", staticmethod(lambda *a, **k: []))
    monkeypatch.setattr(kds.OpenLibrarySearch, "search", staticmethod(lambda *a, **k: []))
    monkeypatch.setattr(kds.FAOSearch, "search", staticmethod(lambda *a, **k: []))

    svc = AutoSourceDiscoveryService(check_access=False)
    results = svc.discover_by_keywords(
        keywords=["agriculture"],
        languages=["en", "hi", "mr"],
        source_types=["wikipedia", "pdf", "web"],
        max_results_per_keyword=2,
    )
    assert len(results) >= 3
    langs = {r.language for r in results}
    assert "hi" in langs or "mr" in langs or "en" in langs
    assert all(r.allowed for r in results)
