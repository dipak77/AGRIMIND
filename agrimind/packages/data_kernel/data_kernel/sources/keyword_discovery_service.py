"""Multilingual agri auto-discovery (EN / HI / MR).

Keyword expansion + live search (Wikipedia, Archive.org, Open Library, FAO)
+ allow-list filter + trust ranking + optional access check.

Implements docs/data-discovery-improvement-plan/keyword_discovery_service.py
using stdlib urllib (no hard httpx dependency).
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from data_kernel.sources.discovery import (
    DEFAULT_ALLOW_LIST,
    DiscoveredSource,
    check_url_access_sync,
    default_seed_catalog,
    discover_sources,
    infer_provider,
    infer_trust_score,
    is_url_allow_listed,
    normalize_license,
)

logger = logging.getLogger(__name__)

USER_AGENT = "AGRIMIND-Bot/1.0 (+https://agrimind.local; agri open-knowledge)"

# ============ KEYWORD EXPANSION - EN / HI / MR ============
AGRI_KEYWORD_MAP: dict[str, dict[str, list[str]]] = {
    "cotton": {
        "en": ["cotton", "cotton farming", "cotton pest"],
        "hi": ["कपास", "कपास की खेती"],
        "mr": ["कापूस", "कापूस शेती"],
    },
    "bollworm": {
        "en": ["bollworm", "cotton bollworm", "Helicoverpa armigera"],
        "hi": ["बोंडवर्म", "गुलाबी सुंडी"],
        "mr": ["बोंडअळी", "गुलाबी बोंडअळी"],
    },
    "soil health": {
        "en": ["soil health", "soil fertility", "soil organic carbon"],
        "hi": ["मिट्टी की सेहत", "भूमि उर्वरता", "मृदा स्वास्थ्य"],
        "mr": ["माती आरोग्य", "जमीन सुपीकता"],
    },
    "irrigation": {
        "en": ["irrigation", "drip irrigation", "water management"],
        "hi": ["सिंचाई", "ड्रिप सिंचाई"],
        "mr": ["सिंचन", "ठिबक सिंचन"],
    },
    "organic farming": {
        "en": ["organic farming", "natural farming", "zero budget natural farming"],
        "hi": ["जैविक खेती", "प्राकृतिक खेती"],
        "mr": ["सेंद्रिय शेती", "नैसर्गिक शेती"],
    },
    "rice": {
        "en": ["rice cultivation", "paddy farming"],
        "hi": ["धान की खेती", "चावल"],
        "mr": ["भात शेती", "तांदूळ"],
    },
    "wheat": {
        "en": ["wheat farming", "wheat cultivation"],
        "hi": ["गेहूं की खेती"],
        "mr": ["गहू शेती"],
    },
    "sugarcane": {
        "en": ["sugarcane farming"],
        "hi": ["गन्ने की खेती"],
        "mr": ["ऊस शेती"],
    },
    "soybean": {
        "en": ["soybean cultivation"],
        "hi": ["सोयाबीन की खेती"],
        "mr": ["सोयाबीन शेती"],
    },
    "pest management": {
        "en": ["integrated pest management", "IPM", "pest control"],
        "hi": ["एकीकृत कीट प्रबंधन", "कीट नियंत्रण"],
        "mr": ["एकात्मिक कीड व्यवस्थापन"],
    },
    "fertilizer": {
        "en": ["fertilizer", "NPK", "biofertilizer"],
        "hi": ["उर्वरक", "खाद"],
        "mr": ["खत", "सेंद्रिय खत"],
    },
    "government scheme": {
        "en": ["PM Kisan", "government scheme agriculture", "crop insurance"],
        "hi": ["पीएम किसान योजना", "कृषि योजना"],
        "mr": ["पीएम किसान योजना", "शेतकरी योजना"],
    },
    "agriculture": {
        "en": ["agriculture", "farming", "crop production"],
        "hi": ["कृषि", "खेती"],
        "mr": ["शेती", "कृषी"],
    },
    "farmer": {
        "en": ["farmer advisory", "smallholder farming"],
        "hi": ["किसान", "किसान सलाह"],
        "mr": ["शेतकरी", "शेतकरी सल्ला"],
    },
}


def expand_keywords(
    base_keywords: list[str],
    languages: list[str] | None = None,
) -> dict[str, list[str]]:
    """Expand base keywords into multilingual agri variants (EN/HI/MR)."""
    languages = languages or ["en", "hi", "mr"]
    expanded: dict[str, list[str]] = {lang: [] for lang in languages}

    for kw in base_keywords:
        kw_lower = kw.lower().strip()
        found = False
        for key, translations in AGRI_KEYWORD_MAP.items():
            flat = " ".join(v for vals in translations.values() for v in vals).lower()
            if kw_lower in key or key in kw_lower or kw_lower in flat or any(
                kw_lower in v.lower() or v.lower() in kw_lower
                for vals in translations.values()
                for v in vals
            ):
                for lang in languages:
                    if lang in translations:
                        expanded[lang].extend(translations[lang])
                found = True
                # don't break — allow multiple map hits for compound queries
        if not found:
            for lang in languages:
                expanded[lang].append(kw)

    for lang in expanded:
        seen: set[str] = set()
        uniq: list[str] = []
        for k in expanded[lang]:
            key = k.lower()
            if key not in seen:
                seen.add(key)
                uniq.append(k)
        expanded[lang] = uniq[:20]
    return expanded


def _http_get_json(url: str, *, timeout: float = 15.0) -> Any:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        raw = resp.read(4_000_000)
    return json.loads(raw.decode("utf-8", errors="replace"))


_AGRI_TITLE_TOKENS = (
    "agricultur", "farm", "farmer", "crop", "soil", "irrigat", "pest", "livestock",
    "horticult", "dairy", "fertiliz", "manure", "agronom", "organic", "seed",
    "wheat", "rice", "cotton", "paddy", "bollworm", "कपास", "कृषि", "खेती",
    "शेती", "कापूस", "सिंचाई", "सिंचन", "मिट्टी", "माती", "उर्वरक", "खत",
)


def _is_agri_text(title: str, snippet: str = "") -> bool:
    blob = f"{title} {snippet}".lower()
    return any(t in blob for t in _AGRI_TITLE_TOKENS)


class WikipediaSearch:
    """Search Wikipedia via MediaWiki API (en / hi / mr)."""

    @staticmethod
    def search(query: str, lang: str = "en", limit: int = 8) -> list[dict[str, Any]]:
        try:
            api = (
                f"https://{lang}.wikipedia.org/w/api.php?action=query&list=search"
                f"&srsearch={urllib.parse.quote(query)}&format=json&srlimit={limit}&utf8=1"
            )
            data = _http_get_json(api)
            results: list[dict[str, Any]] = []
            for item in (data.get("query") or {}).get("search") or []:
                title = str(item.get("title") or "").strip()
                if not title:
                    continue
                snippet = re.sub(r"<[^>]+>", " ", str(item.get("snippet") or ""))
                snippet = re.sub(r"\s+", " ", snippet).strip()
                # HI/MR script pages are domain-relevant even if EN tokens missing
                if lang == "en" and not _is_agri_text(title, snippet):
                    continue
                page_url = (
                    f"https://{lang}.wikipedia.org/wiki/"
                    f"{urllib.parse.quote(title.replace(' ', '_'))}"
                )
                results.append(
                    {
                        "source_url": page_url,
                        "source_type": "wikipedia",
                        "license": "cc-by-sa",
                        "title": title,
                        "snippet": snippet[:400],
                        "provider": "Wikipedia",
                        "language": lang,
                        "trust_score": 80 if lang == "en" else 78,
                        "keywords_matched": [query],
                    }
                )
            return results
        except Exception as exc:
            logger.warning("wikipedia_search_failed q=%s lang=%s err=%s", query, lang, exc)
            return []


class ArchiveOrgSearch:
    """Search Internet Archive for agri PDF books."""

    @staticmethod
    def search(query: str, limit: int = 8) -> list[dict[str, Any]]:
        try:
            agri_guard = (
                "(agriculture OR farming OR agronomy OR soil OR irrigation "
                "OR crop OR livestock OR horticulture)"
            )
            q = f"({query}) AND {agri_guard} AND mediatype:(texts)"
            api = (
                "https://archive.org/advancedsearch.php?"
                f"q={urllib.parse.quote(q)}"
                f"&fl[]=identifier&fl[]=title&fl[]=description&fl[]=downloads"
                f"&rows={max(limit * 2, 8)}&page=1&output=json&sort[]=downloads+desc"
            )
            data = _http_get_json(api, timeout=18.0)
            docs = ((data.get("response") or {}).get("docs")) or []
            results: list[dict[str, Any]] = []
            for doc in docs:
                ident = str(doc.get("identifier") or "").strip()
                if not ident:
                    continue
                title = str(doc.get("title") or ident).strip()
                desc = doc.get("description") or ""
                if isinstance(desc, list):
                    desc = " ".join(str(x) for x in desc)
                desc = re.sub(r"\s+", " ", str(desc)).strip()[:400]
                if not _is_agri_text(title, desc):
                    continue
                pdf_url = f"https://archive.org/download/{ident}/{ident}.pdf"
                results.append(
                    {
                        "source_url": pdf_url,
                        "source_type": "pdf",
                        "license": "cc0",
                        "title": title,
                        "provider": "Internet Archive",
                        "language": "en",
                        "trust_score": 85,
                        "keywords_matched": [query],
                        "meta": {"identifier": ident, "page": f"https://archive.org/details/{ident}"},
                    }
                )
                if len(results) >= limit:
                    break
            return results
        except Exception as exc:
            logger.warning("archive_search_failed q=%s err=%s", query, exc)
            return []


class OpenLibrarySearch:
    """Search Open Library for open agri books / IA PDFs."""

    @staticmethod
    def search(query: str, limit: int = 6) -> list[dict[str, Any]]:
        try:
            q = urllib.parse.quote(f"{query} agriculture farming")
            api = (
                f"https://openlibrary.org/search.json?q={q}"
                f"&fields=title,author_name,first_publish_year,ia,public_scan_b,subject"
                f"&limit={max(limit * 2, 6)}"
            )
            data = _http_get_json(api, timeout=15.0)
            results: list[dict[str, Any]] = []
            for doc in data.get("docs") or []:
                title = str(doc.get("title") or "Untitled").strip()
                subjects = " ".join(str(s) for s in (doc.get("subject") or [])[:12])
                if not _is_agri_text(title, subjects):
                    continue
                ia_list = doc.get("ia") or []
                ia = ia_list[0] if isinstance(ia_list, list) and ia_list else None
                if ia and (doc.get("public_scan_b") or True):
                    pdf_url = f"https://archive.org/download/{ia}/{ia}.pdf"
                    results.append(
                        {
                            "source_url": pdf_url,
                            "source_type": "pdf",
                            "license": "cc0",
                            "title": title,
                            "provider": "Open Library",
                            "language": "en",
                            "trust_score": 82,
                            "keywords_matched": [query],
                            "meta": {"ia": ia, "public_scan": bool(doc.get("public_scan_b"))},
                        }
                    )
                if len(results) >= limit:
                    break
            return results
        except Exception as exc:
            logger.warning("openlibrary_search_failed q=%s err=%s", query, exc)
            return []


class FAOSearch:
    """Curated FAO open PDFs filtered by keyword relevance."""

    CATALOG = [
        {
            "source_url": "https://www.fao.org/3/i6583e/i6583e.pdf",
            "title": "FAO Soil Organic Carbon",
            "keywords": ["soil", "organic", "carbon", "soil health", "मिट्टी", "माती"],
        },
        {
            "source_url": "https://www.fao.org/3/cb0707en/cb0707en.pdf",
            "title": "FAO Crop Production",
            "keywords": ["crop", "production", "farming", "खेती", "शेती"],
        },
        {
            "source_url": "https://www.fao.org/3/y3557e/y3557e.pdf",
            "title": "FAO Irrigation Manual",
            "keywords": ["irrigation", "water", "सिंचाई", "सिंचन"],
        },
        {
            "source_url": "https://www.fao.org/3/i1037e/i1037e.pdf",
            "title": "FAO Conservation Agriculture",
            "keywords": ["conservation", "soil", "organic", "agriculture"],
        },
        {
            "source_url": (
                "https://www.fao.org/fileadmin/templates/wsfs/docs/expert_paper/"
                "How_to_Feed_the_World_in_2050.pdf"
            ),
            "title": "How to Feed the World in 2050",
            "keywords": ["food security", "agriculture", "farming", "feed"],
        },
    ]

    @staticmethod
    def search(query: str, limit: int = 5) -> list[dict[str, Any]]:
        ql = query.lower()
        results: list[dict[str, Any]] = []
        for c in FAOSearch.CATALOG:
            if any(k.lower() in ql or ql in k.lower() for k in c["keywords"]) or ql in c["title"].lower():
                results.append(
                    {
                        "source_url": c["source_url"],
                        "source_type": "pdf",
                        "license": "cc-by",
                        "title": c["title"],
                        "provider": "FAO",
                        "language": "en",
                        "trust_score": 95,
                        "keywords_matched": [query],
                    }
                )
        return results[:limit]


class AutoSourceDiscoveryService:
    """
    Production auto-discovery:
    - Keyword expansion EN/HI/MR
    - Multi-source search (Wikipedia, Archive, Open Library, FAO)
    - Allow-list + trust scoring + optional access check
    - PDF book finder
    """

    def __init__(
        self,
        allow_list: list[str] | None = None,
        check_access: bool = True,
        max_concurrent: int = 6,
    ) -> None:
        self.allow_list = allow_list or list(DEFAULT_ALLOW_LIST)
        self.check_access = check_access
        self.max_concurrent = max_concurrent

    def discover_by_keywords(
        self,
        keywords: list[str],
        languages: list[str] | None = None,
        source_types: list[str] | None = None,
        max_results_per_keyword: int = 5,
        include_seed_catalog: bool = True,
        max_total: int = 50,
    ) -> list[DiscoveredSource]:
        languages = languages or ["en", "hi", "mr"]
        source_types = source_types or ["wikipedia", "pdf", "web"]
        expanded = expand_keywords(keywords, languages)
        logger.info("auto_discovery expanded=%s", expanded)

        all_candidates: list[dict[str, Any]] = []

        if include_seed_catalog:
            seed = default_seed_catalog()
            kws_lower = [k.lower() for k in keywords]
            filtered: list[dict[str, Any]] = []
            for s in seed:
                if s.get("language") in languages or not s.get("language"):
                    title = (s.get("title") or "").lower()
                    url = (s.get("source_url") or "").lower()
                    if not kws_lower or any(kw in title or kw in url for kw in kws_lower):
                        filtered.append(s)
                    elif s.get("language") in ("hi", "mr"):
                        # always surface local-language seeds when those langs requested
                        filtered.append(s)
            if len(filtered) < 4:
                filtered = [s for s in seed if s.get("language") in languages or s.get("language") == "en"]
            all_candidates.extend(filtered)

        # Parallel live searches
        tasks: list[tuple[str, str, str]] = []  # kind, lang, query
        for lang in languages:
            for q in expanded.get(lang, [])[:5]:
                if "wikipedia" in source_types:
                    tasks.append(("wiki", lang, q))
                if "pdf" in source_types and lang == "en":
                    tasks.append(("archive", lang, q))
                    tasks.append(("openlibrary", lang, q))
                if "pdf" in source_types or "web" in source_types:
                    tasks.append(("fao", lang, q))

        def _run(kind: str, lang: str, q: str) -> list[dict[str, Any]]:
            if kind == "wiki":
                return WikipediaSearch.search(q, lang=lang, limit=max_results_per_keyword)
            if kind == "archive":
                return ArchiveOrgSearch.search(f"agriculture {q}", limit=max_results_per_keyword)
            if kind == "openlibrary":
                return OpenLibrarySearch.search(f"agriculture {q}", limit=3)
            if kind == "fao":
                return FAOSearch.search(q, limit=2)
            return []

        with ThreadPoolExecutor(max_workers=max(1, min(self.max_concurrent, 8))) as pool:
            futs = {pool.submit(_run, k, lang, q): (k, lang, q) for k, lang, q in tasks}
            for fut in as_completed(futs):
                try:
                    all_candidates.extend(fut.result() or [])
                except Exception as exc:
                    logger.debug("search_task_failed: %s", exc)

        # Dedup by URL
        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for c in all_candidates:
            url = str(c.get("source_url") or "")
            if not url or url in seen:
                continue
            if "pdf" in source_types and "wikipedia" not in source_types and "web" not in source_types:
                if c.get("source_type") != "pdf":
                    continue
            seen.add(url)
            c["license"] = normalize_license(c.get("license"))
            deduped.append(c)

        discovered = discover_sources(
            deduped,
            allow_list=self.allow_list,
            check_access=self.check_access,
        )
        allowed = [d for d in discovered if d.allowed]
        allowed.sort(
            key=lambda d: d.trust_score + len(d.keywords_matched) * 10,
            reverse=True,
        )
        return allowed[:max_total]

    def find_pdf_books(
        self,
        topic: str,
        max_books: int = 10,
        open_access_only: bool = True,
    ) -> list[DiscoveredSource]:
        candidates: list[dict[str, Any]] = []
        candidates.extend(ArchiveOrgSearch.search(f"agriculture {topic}", limit=max_books))
        candidates.extend(OpenLibrarySearch.search(f"agriculture {topic}", limit=max_books))
        candidates.extend(FAOSearch.search(topic, limit=5))
        classics = [
            {
                "source_url": "https://archive.org/download/cu31924000346686/cu31924000346686.pdf",
                "source_type": "pdf",
                "license": "cc0",
                "title": "Farmers of Forty Centuries (1911)",
                "provider": "Internet Archive",
                "trust_score": 85,
                "language": "en",
            },
            {
                "source_url": "https://archive.org/download/agriculturetextbo00warr/agriculturetextbo00warr.pdf",
                "source_type": "pdf",
                "license": "cc0",
                "title": "Agriculture Textbook",
                "provider": "Internet Archive",
                "trust_score": 84,
                "language": "en",
            },
            {
                "source_url": "https://www.fao.org/3/i6583e/i6583e.pdf",
                "source_type": "pdf",
                "license": "cc-by",
                "title": "FAO Soil Organic Carbon",
                "provider": "FAO",
                "trust_score": 95,
                "language": "en",
            },
        ]
        if any(t in topic.lower() for t in ("soil", "farm", "agri", "crop", "मिट्टी", "माती")):
            candidates.extend(classics)
        discovered = discover_sources(
            candidates,
            allow_list=self.allow_list,
            check_access=self.check_access,
        )
        return [d for d in discovered if d.allowed and d.source_type == "pdf"][:max_books]

    def check_single_url(self, url: str) -> dict[str, Any]:
        access = check_url_access_sync(url)
        allowed = is_url_allow_listed(url, self.allow_list)
        return {
            "url": url,
            "allowed_by_allow_list": allowed,
            "accessible": access.accessible,
            "status_code": access.status_code,
            "content_type": access.content_type,
            "robots_allowed": access.robots_allowed,
            "license_guess": access.license_guess,
            "is_pdf": access.is_pdf,
            "is_trusted": access.is_trusted,
            "trust_score": infer_trust_score(url),
            "provider": infer_provider(url),
            "error": access.error,
        }


def discover_multilingual(
    keywords: list[str],
    *,
    languages: list[str] | None = None,
    check_access: bool = False,
    max_results: int = 40,
    source_types: list[str] | None = None,
) -> dict[str, Any]:
    """Convenience wrapper for API / batch ingest."""
    langs = languages or ["en", "hi", "mr"]
    svc = AutoSourceDiscoveryService(check_access=check_access)
    results = svc.discover_by_keywords(
        keywords=keywords,
        languages=langs,
        source_types=source_types,
        max_total=max_results,
    )
    return {
        "keywords": keywords,
        "languages": langs,
        "expanded": expand_keywords(keywords, langs),
        "count": len(results),
        "sources": [r.to_dict() for r in results],
        "ingest_ready": [
            {
                "source_url": r.source_url,
                "source_type": r.source_type,
                "license": r.license,
                "title": r.title,
                "provider": r.provider,
                "language": r.language,
            }
            for r in results
            if r.allowed
            and (
                not check_access
                or r.access_status in ("ok", "unknown")
            )
        ],
    }


def create_discovery_app():
    """Optional standalone FastAPI app (also integrated in data-ingestion-service).

    Run::
        uvicorn data_kernel.sources.keyword_discovery_service:create_discovery_app \\
            --factory --port 8018
    """
    from fastapi import FastAPI
    from pydantic import BaseModel, Field

    from data_kernel.sources.discovery import default_seed_catalog

    app = FastAPI(
        title="AGRIMIND Auto Discovery Service",
        version="1.1",
        description="EN/HI/MR agri keyword discovery over trusted open sources",
    )

    class DiscoverRequest(BaseModel):
        keywords: list[str] = Field(..., min_length=1)
        languages: list[str] = Field(default_factory=lambda: ["en", "hi", "mr"])
        source_types: list[str] = Field(
            default_factory=lambda: ["wikipedia", "pdf", "web"]
        )
        max_results: int = 40
        check_access: bool = False

    class CheckRequest(BaseModel):
        url: str

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "allow_list_size": len(DEFAULT_ALLOW_LIST),
            "languages": ["en", "hi", "mr"],
        }

    @app.post("/discover")
    async def discover(req: DiscoverRequest):
        svc = AutoSourceDiscoveryService(check_access=req.check_access)
        results = svc.discover_by_keywords(
            keywords=req.keywords,
            languages=req.languages,
            source_types=req.source_types,
            max_total=req.max_results,
        )
        return {
            "count": len(results),
            "expanded": expand_keywords(req.keywords, req.languages),
            "results": [r.to_dict() for r in results],
        }

    @app.post("/discover/pdf-books")
    async def discover_books(topic: str, max_books: int = 10):
        svc = AutoSourceDiscoveryService(check_access=True)
        results = svc.find_pdf_books(topic, max_books=max_books)
        return {"count": len(results), "results": [r.to_dict() for r in results]}

    @app.post("/check-access")
    async def check_access_ep(req: CheckRequest):
        return AutoSourceDiscoveryService().check_single_url(req.url)

    @app.get("/catalog")
    async def catalog():
        return {"count": len(default_seed_catalog()), "catalog": default_seed_catalog()}

    return app
