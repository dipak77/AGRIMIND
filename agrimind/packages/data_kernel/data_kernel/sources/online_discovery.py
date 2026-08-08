"""Online keyword discovery for agri / farmer open sources.

Searches trusted open discovery APIs (no generic SEO crawl):
  - Wikipedia MediaWiki search
  - Open Library (books)
  - Internet Archive (PDF books / texts)
  - Wikimedia Commons (PDF media)
  - Static trusted portal seeds (FAO, USDA, ICAR, India agri)

Then filters by allow-list and optionally probes HTTP access.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urlparse

from data_kernel.sources.agri_taxonomy import (
    keywords_for_categories,
    list_categories,
    match_categories,
)
from data_kernel.sources.discovery import DEFAULT_ALLOW_LIST, is_url_allow_listed

logger = logging.getLogger(__name__)

USER_AGENT = "AgrimindDiscovery/0.2 (+https://agrimind.local; agri open-knowledge research)"


# ---------------------------------------------------------------------------
# Discovery service registry (what we call online)
# ---------------------------------------------------------------------------

DISCOVERY_SERVICES: list[dict[str, Any]] = [
    {
        "id": "wikipedia_search",
        "name": "Wikipedia (MediaWiki Search)",
        "kind": "encyclopedia",
        "base_url": "https://en.wikipedia.org/w/api.php",
        "license_hint": "cc-by-sa",
        "formats": ["wikipedia", "web", "pdf"],
        "auth": "none",
        "agri_focus": "General agri knowledge pages; good for IPM, soil, irrigation",
        "status": "online",
    },
    {
        "id": "open_library",
        "name": "Open Library",
        "kind": "books",
        "base_url": "https://openlibrary.org/search.json",
        "license_hint": "mixed_open",
        "formats": ["web", "pdf"],
        "auth": "none",
        "agri_focus": "Agri textbooks, handbooks, public-domain farm books",
        "status": "online",
    },
    {
        "id": "internet_archive",
        "name": "Internet Archive",
        "kind": "books_archive",
        "base_url": "https://archive.org/advancedsearch.php",
        "license_hint": "mixed_public_domain",
        "formats": ["pdf", "web"],
        "auth": "none",
        "agri_focus": "Scanned agriculture books and FAO/gov PDFs",
        "status": "online",
    },
    {
        "id": "commons_pdf",
        "name": "Wikimedia Commons (PDF)",
        "kind": "media",
        "base_url": "https://commons.wikimedia.org/w/api.php",
        "license_hint": "cc-by-sa",
        "formats": ["pdf"],
        "auth": "none",
        "agri_focus": "Open PDF leaflets and diagrams for agriculture",
        "status": "online",
    },
    {
        "id": "fao_open",
        "name": "FAO Open Knowledge (seed portals)",
        "kind": "gov_portal",
        "base_url": "https://www.fao.org/",
        "license_hint": "government_open",
        "formats": ["pdf", "web"],
        "auth": "none",
        "agri_focus": "UN FAO publications, stats, expert papers",
        "status": "seeded",  # keyword match against known open URLs + portal roots
    },
    {
        "id": "usda_open",
        "name": "USDA open portals",
        "kind": "gov_portal",
        "base_url": "https://www.usda.gov/",
        "license_hint": "government_open",
        "formats": ["web", "pdf"],
        "auth": "none",
        "agri_focus": "US federal soil, NASS, ERS agri data (public domain)",
        "status": "seeded",
    },
    {
        "id": "india_agri_gov",
        "name": "India agri / ICAR / farmer.gov",
        "kind": "gov_portal",
        "base_url": "https://icar.org.in/",
        "license_hint": "government_open",
        "formats": ["web", "pdf"],
        "auth": "none",
        "agri_focus": "ICAR, agri coop, farmer schemes (gov.in)",
        "status": "seeded",
    },
]


# Keyword → trusted open seeds (always agri-domain, allow-listed).
TRUSTED_PORTAL_SEEDS: list[dict[str, Any]] = [
    {
        "source_url": "https://www.fao.org/fileadmin/templates/wsfs/docs/expert_paper/How_to_Feed_the_World_in_2050.pdf",
        "source_type": "pdf",
        "license": "government_open",
        "title": "How to Feed the World in 2050 (FAO)",
        "provider": "FAO",
        "service": "fao_open",
        "match_keywords": ["feed the world", "food security", "fao", "agriculture textbook"],
    },
    {
        "source_url": "https://www.fao.org/faostat/en/#home",
        "source_type": "web",
        "license": "government_open",
        "title": "FAOSTAT agriculture statistics",
        "provider": "FAO",
        "service": "fao_open",
        "match_keywords": ["statistics", "crop production", "markets", "fao"],
    },
    {
        "source_url": "https://www.nrcs.usda.gov/conservation-basics/natural-resource-concerns/soils/soil-health",
        "source_type": "web",
        "license": "government_open",
        "title": "USDA NRCS Soil Health",
        "provider": "USDA",
        "service": "usda_open",
        "match_keywords": ["soil health", "soil fertility", "conservation agriculture"],
    },
    {
        "source_url": "https://www.ers.usda.gov/",
        "source_type": "web",
        "license": "government_open",
        "title": "USDA Economic Research Service",
        "provider": "USDA",
        "service": "usda_open",
        "match_keywords": ["agricultural marketing", "farm income", "commodity price"],
    },
    {
        "source_url": "https://www.nass.usda.gov/",
        "source_type": "web",
        "license": "government_open",
        "title": "USDA NASS agricultural statistics",
        "provider": "USDA",
        "service": "usda_open",
        "match_keywords": ["statistics", "crop production", "livestock"],
    },
    {
        "source_url": "https://icar.org.in/",
        "source_type": "web",
        "license": "government_open",
        "title": "Indian Council of Agricultural Research",
        "provider": "ICAR",
        "service": "india_agri_gov",
        "match_keywords": ["icar", "india", "crop", "research", "extension"],
    },
    {
        "source_url": "https://farmer.gov.in/",
        "source_type": "web",
        "license": "government_open",
        "title": "Farmer.gov.in (India farmer portal)",
        "provider": "GoI",
        "service": "india_agri_gov",
        "match_keywords": ["farmer", "scheme", "advisory", "india", "pm kisan"],
    },
    {
        "source_url": "https://agricoop.gov.in/",
        "source_type": "web",
        "license": "government_open",
        "title": "Ministry of Agriculture & Farmers Welfare (India)",
        "provider": "GoI",
        "service": "india_agri_gov",
        "match_keywords": ["policy", "scheme", "farmer", "agriculture india"],
    },
    {
        "source_url": "https://en.wikipedia.org/api/rest_v1/page/pdf/Agriculture",
        "source_type": "pdf",
        "license": "cc-by-sa",
        "title": "Agriculture (Wikipedia book PDF)",
        "provider": "Wikipedia",
        "service": "wikipedia_search",
        "match_keywords": ["agriculture textbook", "agriculture", "farming"],
    },
]


@dataclass
class AccessCheck:
    url: str
    reachable: bool
    status_code: int | None = None
    content_type: str | None = None
    content_length: int | None = None
    is_pdf: bool = False
    error: str | None = None
    method: str = "HEAD"


@dataclass
class OnlineHit:
    source_url: str
    source_type: str
    title: str
    provider: str
    service: str
    license: str = "unknown"
    allowed: bool = False
    reason: str | None = None
    snippet: str | None = None
    categories: list[str] = field(default_factory=list)
    keywords_matched: list[str] = field(default_factory=list)
    score: float = 0.0
    access: dict[str, Any] | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def list_discovery_services() -> list[dict[str, Any]]:
    return list(DISCOVERY_SERVICES)


def _http_get_json(url: str, *, timeout: float = 12.0) -> Any:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        raw = resp.read(4_000_000)
    return json.loads(raw.decode("utf-8", errors="replace"))


def check_access(url: str, *, timeout: float = 6.0) -> AccessCheck:
    """Lightweight HEAD (fallback GET range) access probe for open sources."""
    headers = {"User-Agent": USER_AGENT}
    # Prefer HEAD
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                status = int(getattr(resp, "status", 200) or 200)
                ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip()
                clen_raw = resp.headers.get("Content-Length")
                clen = int(clen_raw) if clen_raw and clen_raw.isdigit() else None
                if method == "GET":
                    # only need headers; discard body quickly
                    resp.read(64)
                is_pdf = "pdf" in ctype.lower() or url.lower().endswith(".pdf")
                ok = 200 <= status < 400
                return AccessCheck(
                    url=url,
                    reachable=ok,
                    status_code=status,
                    content_type=ctype or None,
                    content_length=clen,
                    is_pdf=is_pdf,
                    method=method,
                )
        except urllib.error.HTTPError as exc:
            if method == "HEAD" and exc.code in (403, 405, 501):
                continue
            return AccessCheck(
                url=url,
                reachable=False,
                status_code=getattr(exc, "code", None),
                error=str(exc),
                method=method,
            )
        except Exception as exc:
            if method == "HEAD":
                continue
            return AccessCheck(
                url=url,
                reachable=False,
                error=str(exc)[:240],
                method=method,
            )
    return AccessCheck(url=url, reachable=False, error="unreachable", method="HEAD")


def _wiki_search(query: str, *, lang: str = "en", limit: int = 5) -> list[OnlineHit]:
    q = urllib.parse.quote(query)
    api = (
        f"https://{lang}.wikipedia.org/w/api.php?action=query&list=search"
        f"&srsearch={q}&srlimit={limit}&format=json&utf8=1"
    )
    data = _http_get_json(api)
    hits: list[OnlineHit] = []
    for row in (data.get("query") or {}).get("search") or []:
        title = str(row.get("title") or "").strip()
        if not title:
            continue
        snippet = re.sub(r"<[^>]+>", " ", str(row.get("snippet") or ""))
        snippet = re.sub(r"\s+", " ", snippet).strip()
        if not _is_agri_text(title, snippet):
            continue
        slug = title.replace(" ", "_")
        url = f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(slug)}"
        hits.append(
            OnlineHit(
                source_url=url,
                source_type="wikipedia",
                title=title,
                provider="Wikipedia",
                service="wikipedia_search",
                license="cc-by-sa",
                snippet=snippet[:400],
                score=float(row.get("score") or 0) or 1.0,
                meta={"pageid": row.get("pageid"), "lang": lang, "wordcount": row.get("wordcount")},
            )
        )
        # also offer PDF export of the page
        pdf_url = f"https://{lang}.wikipedia.org/api/rest_v1/page/pdf/{urllib.parse.quote(slug)}"
        hits.append(
            OnlineHit(
                source_url=pdf_url,
                source_type="pdf",
                title=f"{title} (Wikipedia PDF export)",
                provider="Wikipedia",
                service="wikipedia_search",
                license="cc-by-sa",
                snippet=snippet[:200],
                score=0.8,
                meta={"pageid": row.get("pageid"), "lang": lang, "export": "pdf"},
            )
        )
    return hits


def _open_library_search(query: str, *, limit: int = 5) -> list[OnlineHit]:
    # Bias search toward agriculture subject
    q = urllib.parse.quote(f"{query} agriculture farming")
    api = f"https://openlibrary.org/search.json?q={q}&limit={max(limit * 2, 6)}"
    data = _http_get_json(api, timeout=15.0)
    hits: list[OnlineHit] = []
    for doc in data.get("docs") or []:
        title = str(doc.get("title") or "Untitled").strip()
        key = str(doc.get("key") or "")  # /works/OLxxxxW
        if not key:
            continue
        subjects = " ".join(str(s) for s in (doc.get("subject") or [])[:12])
        if not _is_agri_text(title, subjects):
            continue
        url = f"https://openlibrary.org{key}"
        authors = ", ".join((doc.get("author_name") or [])[:3])
        has_fulltext = bool(doc.get("has_fulltext"))
        ia = doc.get("ia") or []
        # Prefer direct archive PDF when Internet Archive id present
        if ia:
            ia_id = ia[0]
            pdf_url = f"https://archive.org/download/{ia_id}/{ia_id}.pdf"
            hits.append(
                OnlineHit(
                    source_url=pdf_url,
                    source_type="pdf",
                    title=f"{title} (Archive PDF via Open Library)",
                    provider="Open Library / Internet Archive",
                    service="open_library",
                    license="mixed_public_domain" if has_fulltext else "unknown",
                    snippet=f"Authors: {authors}"[:400],
                    score=2.0 if has_fulltext else 1.0,
                    meta={
                        "work_key": key,
                        "ia": ia_id,
                        "has_fulltext": has_fulltext,
                        "first_publish_year": doc.get("first_publish_year"),
                    },
                )
            )
        hits.append(
            OnlineHit(
                source_url=url,
                source_type="web",
                title=title,
                provider="Open Library",
                service="open_library",
                license="mixed_open",
                snippet=f"Authors: {authors}; fulltext={has_fulltext}"[:400],
                score=1.2 if has_fulltext else 0.7,
                meta={
                    "work_key": key,
                    "has_fulltext": has_fulltext,
                    "first_publish_year": doc.get("first_publish_year"),
                },
            )
        )
    return hits


# Hard agri tokens — at least one must appear in title/snippet for non-seed hits
_AGRI_TITLE_TOKENS = (
    "agricultur", "farm", "farmer", "crop", "soil", "irrigat", "pest", "livestock",
    "horticult", "dairy", "aquacult", "fertiliz", "manure", "agronom", "plant path",
    "organic farm", "seed ", "seeds", "wheat", "rice", "cotton", "cattle", "poultry",
    "fodder", "harvest", "cultivat", "agro", "extension", "veterinary", "pasture",
    "compost", "paddy", "millet", "soybean", "tractor", "mandi", "kisan", "icar",
    "fao", "usda", "nrcs", "greenhouse", "orchard", "vegetable", "fruit farm",
)

_BLOCK_TITLE = (
    "nuclear", "communism", "paranormal", "cia reading", "weapon", "propaganda",
    "porn", "erotic", "bitcoin", "cryptocurrency", "marvel", "superhero",
)


def _is_agri_text(title: str, snippet: str = "") -> bool:
    blob = f"{title} {snippet}".lower()
    if any(b in blob for b in _BLOCK_TITLE):
        return False
    return any(t in blob for t in _AGRI_TITLE_TOKENS)


def _internet_archive_search(query: str, *, limit: int = 5) -> list[OnlineHit]:
    # Prefer texts/media with PDF for agriculture — force agri subject terms
    agri_guard = (
        "(agriculture OR farming OR agronomy OR \"soil fertility\" OR irrigation "
        "OR \"crop production\" OR livestock OR horticulture OR \"plant pathology\")"
    )
    q = f'({query}) AND {agri_guard} AND mediatype:(texts) AND format:(PDF)'
    # archive advancedsearch uses repeated fl[] — build manually
    api = (
        "https://archive.org/advancedsearch.php?"
        f"q={urllib.parse.quote(q)}"
        f"&fl[]=identifier&fl[]=title&fl[]=description&fl[]=downloads"
        f"&rows={max(limit * 3, 8)}&page=1&output=json&sort[]=downloads+desc"
    )
    data = _http_get_json(api, timeout=18.0)
    docs = ((data.get("response") or {}).get("docs")) or []
    hits: list[OnlineHit] = []
    for doc in docs:
        ident = str(doc.get("identifier") or "").strip()
        if not ident:
            continue
        title = str(doc.get("title") or ident).strip()
        desc = str(doc.get("description") or "")
        if isinstance(doc.get("description"), list):
            desc = " ".join(str(x) for x in doc["description"])
        desc = re.sub(r"\s+", " ", desc).strip()[:400]
        if not _is_agri_text(title, desc):
            continue
        pdf_url = f"https://archive.org/download/{ident}/{ident}.pdf"
        page_url = f"https://archive.org/details/{ident}"
        hits.append(
            OnlineHit(
                source_url=pdf_url,
                source_type="pdf",
                title=title,
                provider="Internet Archive",
                service="internet_archive",
                license="mixed_public_domain",
                snippet=desc,
                score=float(doc.get("downloads") or 0) / 1000.0 + 1.0,
                meta={"identifier": ident, "downloads": doc.get("downloads"), "page": page_url},
            )
        )
        if len(hits) >= limit:
            break
    return hits


def _commons_pdf_search(query: str, *, limit: int = 4) -> list[OnlineHit]:
    q = urllib.parse.quote(f"filetype:pdf {query}")
    api = (
        "https://commons.wikimedia.org/w/api.php?action=query&list=search"
        f"&srsearch={q}&srnamespace=6&srlimit={limit}&format=json"
    )
    data = _http_get_json(api)
    hits: list[OnlineHit] = []
    for row in (data.get("query") or {}).get("search") or []:
        title = str(row.get("title") or "").strip()  # File:Something.pdf
        if not title.lower().endswith(".pdf"):
            continue
        file_name = title.split(":", 1)[-1]
        # Special:FilePath redirects to actual binary
        url = f"https://commons.wikimedia.org/wiki/Special:FilePath/{urllib.parse.quote(file_name)}"
        page = f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
        hits.append(
            OnlineHit(
                source_url=url,
                source_type="pdf",
                title=file_name,
                provider="Wikimedia Commons",
                service="commons_pdf",
                license="cc-by-sa",
                snippet=re.sub(r"<[^>]+>", " ", str(row.get("snippet") or ""))[:300],
                score=1.0,
                meta={"commons_page": page},
            )
        )
    return hits


def _seed_matches(keywords: list[str]) -> list[OnlineHit]:
    hits: list[OnlineHit] = []
    kw_blob = " ".join(keywords).lower()
    for seed in TRUSTED_PORTAL_SEEDS:
        matched = [
            m for m in seed.get("match_keywords") or [] if str(m).lower() in kw_blob or any(
                str(m).lower() in k for k in keywords
            )
        ]
        # always include core portals on broad agri queries
        if not matched and any(k in kw_blob for k in ("agricultur", "farm", "crop", "soil", "farmer")):
            matched = ["agriculture"]
        if not matched:
            continue
        hits.append(
            OnlineHit(
                source_url=str(seed["source_url"]),
                source_type=str(seed.get("source_type") or "web"),
                title=str(seed.get("title") or seed["source_url"]),
                provider=str(seed.get("provider") or "portal"),
                service=str(seed.get("service") or "seed"),
                license=str(seed.get("license") or "government_open"),
                snippet="Trusted open agri portal seed",
                score=1.5,
                keywords_matched=matched[:5],
                meta={"seed": True},
            )
        )
    return hits


def _search_one(
    service_id: str,
    query: str,
    *,
    limit: int,
    lang: str,
) -> list[OnlineHit]:
    try:
        if service_id == "wikipedia_search":
            return _wiki_search(query, lang=lang, limit=limit)
        if service_id == "open_library":
            return _open_library_search(query, limit=limit)
        if service_id == "internet_archive":
            return _internet_archive_search(query, limit=limit)
        if service_id == "commons_pdf":
            return _commons_pdf_search(query, limit=limit)
        if service_id in ("fao_open", "usda_open", "india_agri_gov"):
            return []  # seeds handled separately
    except Exception as exc:
        logger.warning("discovery_service_failed service=%s q=%s err=%s", service_id, query, exc)
    return []


def discover_online(
    *,
    query: str | None = None,
    categories: list[str] | None = None,
    keywords: list[str] | None = None,
    services: list[str] | None = None,
    lang: str = "en",
    per_keyword_limit: int = 3,
    max_keywords: int = 8,
    max_results: int = 40,
    allow_list: list[str] | None = None,
    check_access_flag: bool = True,
    pdf_only: bool = False,
    books_bias: bool = False,
    max_access_checks: int = 20,
    workers: int = 6,
) -> dict[str, Any]:
    """
    Keyword-based online discovery for agri/farmer domain only.

    Returns hits with allow-list + optional access probe results.
    """
    free = [query] if query and query.strip() else []
    kws = keywords_for_categories(
        categories,
        extra_keywords=(keywords or []) + free,
        limit_per_category=4,
    )
    if books_bias or pdf_only:
        for bk in (
            "agriculture textbook",
            "handbook of agriculture",
            "soil science",
            "agronomy",
            "plant pathology",
            "farming",
        ):
            if bk not in kws:
                kws.append(bk)
    kws = kws[: max(1, max_keywords)]

    svc_ids = services or [
        "wikipedia_search",
        "open_library",
        "internet_archive",
        "commons_pdf",
        "fao_open",
        "usda_open",
        "india_agri_gov",
    ]
    # live search services
    live_ids = [s for s in svc_ids if s in (
        "wikipedia_search", "open_library", "internet_archive", "commons_pdf"
    )]
    if books_bias:
        # prefer book services first
        live_ids = [s for s in ("open_library", "internet_archive", "commons_pdf", "wikipedia_search") if s in live_ids]

    raw_hits: list[OnlineHit] = []
    errors: list[dict[str, str]] = []

    # parallel keyword × service fan-out (bounded)
    tasks: list[tuple[str, str]] = []
    for kw in kws:
        for sid in live_ids:
            tasks.append((sid, kw))

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 8))) as pool:
        futs = {
            pool.submit(_search_one, sid, kw, limit=per_keyword_limit, lang=lang): (sid, kw)
            for sid, kw in tasks
        }
        for fut in as_completed(futs):
            sid, kw = futs[fut]
            try:
                for hit in fut.result() or []:
                    hit.keywords_matched = list(set(hit.keywords_matched + [kw]))
                    raw_hits.append(hit)
            except Exception as exc:
                errors.append({"service": sid, "keyword": kw, "error": str(exc)[:200]})

    # trusted portal seeds
    if any(s in svc_ids for s in ("fao_open", "usda_open", "india_agri_gov")):
        raw_hits.extend(_seed_matches(kws))

    # allow-list + agri category tags + dedupe by URL
    allow = allow_list or list(DEFAULT_ALLOW_LIST)
    by_url: dict[str, OnlineHit] = {}
    seed_services = {"fao_open", "usda_open", "india_agri_gov"}
    for hit in raw_hits:
        if pdf_only and hit.source_type != "pdf":
            continue
        # Domain gate: agri/farmer only (seeds always trusted)
        if hit.service not in seed_services and not hit.meta.get("seed"):
            if not _is_agri_text(hit.title, hit.snippet or ""):
                continue
        ok = is_url_allow_listed(hit.source_url, allow)
        hit.allowed = ok
        hit.reason = None if ok else "source_not_allow_listed"
        hit.categories = match_categories(f"{hit.title} {hit.snippet or ''}")
        prev = by_url.get(hit.source_url)
        if prev is None or hit.score > prev.score:
            by_url[hit.source_url] = hit

    hits = sorted(by_url.values(), key=lambda h: (h.allowed, h.score), reverse=True)

    # access checks (top N allowed only to avoid hammering)
    if check_access_flag:
        to_check = [h for h in hits if h.allowed][:max_access_checks]
        with ThreadPoolExecutor(max_workers=max(1, min(workers, 8))) as pool:
            fmap = {pool.submit(check_access, h.source_url): h for h in to_check}
            for fut in as_completed(fmap):
                h = fmap[fut]
                try:
                    ac = fut.result()
                    h.access = asdict(ac)
                    if not ac.reachable:
                        h.reason = h.reason or "access_check_failed"
                except Exception as exc:
                    h.access = {"reachable": False, "error": str(exc)[:200]}

    hits = hits[: max_results]
    allowed_n = sum(1 for h in hits if h.allowed)
    reachable_n = sum(1 for h in hits if (h.access or {}).get("reachable"))
    pdf_n = sum(1 for h in hits if h.source_type == "pdf")

    return {
        "query": query,
        "categories_requested": categories or [],
        "keywords_used": kws,
        "services_used": svc_ids,
        "discovery_services": [s for s in DISCOVERY_SERVICES if s["id"] in svc_ids],
        "taxonomy_categories": list_categories(),
        "count": len(hits),
        "allowed_count": allowed_n,
        "reachable_count": reachable_n,
        "pdf_count": pdf_n,
        "errors": errors[:20],
        "sources": [h.to_dict() for h in hits],
        "ingest_ready": [
            {
                "source_url": h.source_url,
                "source_type": h.source_type,
                "license": h.license,
                "title": h.title,
                "provider": h.provider,
            }
            for h in hits
            if h.allowed and (not check_access_flag or (h.access or {}).get("reachable"))
        ],
        "note": (
            "Agri/farmer domain keyword discovery over trusted open APIs only. "
            "Use ingest_ready with POST /v1/ingest/batch sources=..."
        ),
    }
