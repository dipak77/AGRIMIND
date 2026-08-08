"""Trusted agri source discovery: allow-list, trust scoring, seed catalog, access.

Implements the data-discovery-improvement plan for EN / HI / MR acquisition.
"""

from __future__ import annotations

import logging
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

logger = logging.getLogger(__name__)

USER_AGENT = "AGRIMIND-Bot/1.0 (+https://agrimind.local; agri open-knowledge)"

# ============ TRUSTED ALLOW LIST (expanded) ============
DEFAULT_ALLOW_LIST = [
    # India Government / ICAR / agri universities
    "icar.org.in",
    "icar.gov.in",
    "iari.res.in",
    "iihr.res.in",
    "gov.in",
    "nic.in",
    "agricoop.gov.in",
    "farmer.gov.in",
    "mkisan.gov.in",
    "data.gov.in",
    "agmarknet.gov.in",
    "soilhealth.dac.gov.in",
    "pmkisan.gov.in",
    "agricoop.nic.in",
    "vikaspedia.in",
    "india.gov.in",
    "tnau.ac.in",
    "pau.edu",
    "mpkv.ac.in",
    "agriculture.gov.in",
    "nhb.gov.in",
    "apeda.gov.in",
    # UN / FAO / World Bank
    "fao.org",
    "openknowledge.fao.org",
    "faostat.fao.org",
    "un.org",
    "undp.org",
    "worldbank.org",
    "openknowledge.worldbank.org",
    "data.worldbank.org",
    # US open agri
    "usda.gov",
    "nrcs.usda.gov",
    "ers.usda.gov",
    "nass.usda.gov",
    "ars.usda.gov",
    "nal.usda.gov",
    # CGIAR / international research
    "cgiar.org",
    "irri.org",
    "icrisat.org",
    "cimmyt.org",
    "ifpri.org",
    "iwmi.cgiar.org",
    "worldagroforestry.org",
    "cipotato.org",
    "iita.org",
    "oar.icrisat.org",
    # Wikipedia / Wikimedia
    "wikipedia.org",
    "wikimedia.org",
    "wikidata.org",
    "wikisource.org",
    "wikibooks.org",
    "commons.wikimedia.org",
    # Open books / archives
    "archive.org",
    "openlibrary.org",
    "gutenberg.org",
    "oapen.org",
    "doabooks.org",
    # Open science (tier 2)
    "ncbi.nlm.nih.gov",
    "pubmed.ncbi.nlm.nih.gov",
    "europepmc.org",
    "doaj.org",
    "core.ac.uk",
    "plos.org",
    "frontiersin.org",
    # Extension
    "extension.org",
    "plantvillage.psu.edu",
    "ipm.ucanr.edu",
    "eorganic.org",
    # Weather India
    "imd.gov.in",
    "mausam.imd.gov.in",
    # Local / tests
    "example.com",
    "localhost",
    "127.0.0.1",
]

# Domain suffix → pipeline-compatible license
LICENSE_BY_DOMAIN = {
    "gov.in": "government_open",
    "nic.in": "government_open",
    "fao.org": "cc-by",
    "usda.gov": "cc0",
    "wikipedia.org": "cc-by-sa",
    "wikimedia.org": "cc-by-sa",
    "archive.org": "cc0",
    "gutenberg.org": "cc0",
    "icar.org.in": "government_open",
    "cgiar.org": "cc-by",
    "irri.org": "cc-by",
    "icrisat.org": "cc-by",
    "data.gov.in": "government_open",
    "worldbank.org": "cc-by",
    "openlibrary.org": "cc0",
}

TRUST_SCORE = {
    "icar.org.in": 95,
    "gov.in": 90,
    "fao.org": 95,
    "usda.gov": 92,
    "wikipedia.org": 80,
    "archive.org": 85,
    "cgiar.org": 90,
    "irri.org": 92,
    "icrisat.org": 90,
    "data.gov.in": 88,
    "openlibrary.org": 82,
}

# Normalize external license strings to pipeline ALLOWED set
_LICENSE_NORMALIZE = {
    "cc-by-sa-4.0": "cc-by-sa",
    "cc-by-sa4.0": "cc-by-sa",
    "cc_by_sa_4.0": "cc-by-sa",
    "cc-by-4.0": "cc-by",
    "cc-by-3.0-igo": "cc-by",
    "cc_by_3.0_igo": "cc-by",
    "cc0-us-gov-pd": "cc0",
    "cc0_us_gov_pd": "cc0",
    "godl-india": "government_open",
    "public-domain": "cc0",
    "public_domain": "cc0",
    "public-domain-or-cc": "cc0",
    "mixed_public_domain": "cc0",
    "mixed_open": "cc-by",
}


def normalize_license(lic: str | None) -> str:
    """Map external license tags to pipeline ALLOWED forms (cc-by, government_open, …)."""
    raw = (lic or "unknown").strip().lower()
    key = raw.replace(" ", "_")
    if key in _LICENSE_NORMALIZE:
        return _LICENSE_NORMALIZE[key]
    alt = key.replace("_", "-")
    if alt in _LICENSE_NORMALIZE:
        return _LICENSE_NORMALIZE[alt]
    return raw


@dataclass
class DiscoveredSource:
    source_url: str
    source_type: str
    license: str = "unknown"
    allowed: bool = True
    reason: str | None = None
    title: str | None = None
    provider: str | None = None
    language: str = "en"
    trust_score: int = 50
    access_status: str = "unknown"
    content_type: str | None = None
    size_bytes: int | None = None
    last_checked: float = field(default_factory=time.time)
    keywords_matched: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


@dataclass
class AccessCheckResult:
    url: str
    accessible: bool
    status_code: int | None = None
    content_type: str | None = None
    size_bytes: int | None = None
    robots_allowed: bool = True
    license_guess: str = "unknown"
    error: str | None = None
    final_url: str | None = None
    is_pdf: bool = False
    is_trusted: bool = False
    method: str = "HEAD"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def is_url_allow_listed(url: str, allow_list: list[str] | None = None) -> bool:
    allow = allow_list or DEFAULT_ALLOW_LIST
    host = (urlparse(url).netloc or "").lower().split(":")[0]
    if host in ("", "localhost", "127.0.0.1"):
        return True
    for a in allow:
        a = a.lower().strip().lstrip(".")
        if not a:
            continue
        if host == a or host.endswith("." + a):
            return True
    return False


def infer_license(url: str) -> str:
    host = (urlparse(url).netloc or "").lower()
    for domain, lic in LICENSE_BY_DOMAIN.items():
        if host == domain or host.endswith("." + domain) or domain in host:
            return lic
    if url.lower().endswith(".pdf"):
        return "unknown"
    return "unknown"


def infer_trust_score(url: str) -> int:
    host = (urlparse(url).netloc or "").lower()
    for domain, score in TRUST_SCORE.items():
        if host == domain or host.endswith("." + domain) or domain in host:
            return score
    if host.endswith(".gov.in") or host.endswith(".gov"):
        return 85
    if "wikipedia.org" in host:
        return 80
    if "archive.org" in host:
        return 85
    return 50


def infer_provider(url: str) -> str:
    host = (urlparse(url).netloc or "").lower()
    if "icar" in host:
        return "ICAR"
    if "fao.org" in host:
        return "FAO"
    if "usda" in host or "nrcs" in host or "ers.usda" in host or "nass.usda" in host:
        return "USDA"
    if "wikipedia" in host or "wikimedia" in host:
        return "Wikipedia"
    if "archive.org" in host:
        return "Internet Archive"
    if "openlibrary" in host:
        return "Open Library"
    if any(x in host for x in ("cgiar", "irri", "icrisat", "cimmyt", "ifpri")):
        return "CGIAR"
    if host.endswith(".gov.in") or "gov.in" in host:
        return "India Govt"
    if "worldbank" in host:
        return "World Bank"
    if "gutenberg" in host:
        return "Project Gutenberg"
    parts = host.split(".")
    return (parts[-2] if len(parts) >= 2 else host).upper()


_robots_cache: dict[str, RobotFileParser | bool] = {}


def check_robots_txt(url: str, user_agent: str = USER_AGENT) -> bool:
    """Return True if robots.txt allows fetch (fail-open on network errors)."""
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return True
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        cached = _robots_cache.get(robots_url)
        if cached is True:
            return True
        if isinstance(cached, RobotFileParser):
            return bool(cached.can_fetch(user_agent, url))
        rp = RobotFileParser()
        rp.set_url(robots_url)
        try:
            rp.read()
            _robots_cache[robots_url] = rp
            return bool(rp.can_fetch(user_agent, url))
        except Exception:
            _robots_cache[robots_url] = True  # fail-open
            return True
    except Exception:
        return True


def check_url_access_sync(url: str, timeout: float = 8.0) -> AccessCheckResult:
    """HEAD (fallback GET) access probe without requiring httpx."""
    robots_allowed = check_robots_txt(url)
    headers = {"User-Agent": USER_AGENT}
    last_err: str | None = None
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                status = int(getattr(resp, "status", 200) or 200)
                ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip()
                clen_raw = resp.headers.get("Content-Length")
                size = int(clen_raw) if clen_raw and str(clen_raw).isdigit() else None
                final = str(resp.geturl() or url)
                if method == "GET":
                    resp.read(256)
                is_pdf = "pdf" in ctype.lower() or url.lower().endswith(".pdf")
                accessible = (200 <= status < 400) and robots_allowed
                return AccessCheckResult(
                    url=url,
                    accessible=accessible,
                    status_code=status,
                    content_type=ctype or None,
                    size_bytes=size,
                    robots_allowed=robots_allowed,
                    license_guess=infer_license(url),
                    final_url=final,
                    is_pdf=is_pdf,
                    is_trusted=is_url_allow_listed(url),
                    method=method,
                )
        except urllib.error.HTTPError as exc:
            if method == "HEAD" and exc.code in (403, 405, 501):
                continue
            return AccessCheckResult(
                url=url,
                accessible=False,
                status_code=getattr(exc, "code", None),
                robots_allowed=robots_allowed,
                license_guess=infer_license(url),
                error=str(exc)[:200],
                is_trusted=is_url_allow_listed(url),
                is_pdf=url.lower().endswith(".pdf"),
                method=method,
            )
        except Exception as exc:
            last_err = str(exc)[:200]
            if method == "HEAD":
                continue
            return AccessCheckResult(
                url=url,
                accessible=False,
                robots_allowed=robots_allowed,
                license_guess=infer_license(url),
                error=last_err,
                is_trusted=is_url_allow_listed(url),
                method=method,
            )
    return AccessCheckResult(
        url=url,
        accessible=False,
        robots_allowed=robots_allowed,
        license_guess=infer_license(url),
        error=last_err or "unreachable",
        is_trusted=is_url_allow_listed(url),
    )


def discover_sources(
    candidates: list[dict[str, Any]],
    *,
    allow_list: list[str] | None = None,
    check_access: bool = False,
) -> list[DiscoveredSource]:
    """
    Filter candidates by allow-list (+ optional live access check).
    Each candidate: {source_url, source_type?, license?, title?, language?, ...}
    """
    out: list[DiscoveredSource] = []
    for c in candidates:
        url = str(c.get("source_url") or c.get("url") or "")
        if not url:
            continue
        st = str(c.get("source_type") or "web")
        lic = normalize_license(str(c.get("license") or infer_license(url)))
        title = c.get("title")
        provider = c.get("provider") or infer_provider(url)
        lang = str(c.get("language") or c.get("lang") or "en")
        keywords = list(c.get("keywords_matched") or c.get("keywords") or [])

        allowed = is_url_allow_listed(url, allow_list)
        trust = int(c.get("trust_score") or infer_trust_score(url))
        reason = None if allowed else "source_not_allow_listed"
        access_status = "unknown"
        content_type = None
        size_bytes = None

        if check_access:
            chk = check_url_access_sync(url)
            access_status = "ok" if chk.accessible else f"blocked:{chk.error or chk.status_code}"
            content_type = chk.content_type
            size_bytes = chk.size_bytes
            if not chk.robots_allowed:
                allowed = False
                reason = "robots_denied"
                access_status = "robots_denied"
            elif allowed and not chk.accessible:
                # keep allow-list yes but surface access failure
                reason = reason or "access_check_failed"

        out.append(
            DiscoveredSource(
                source_url=url,
                source_type=st,
                license=lic,
                allowed=allowed,
                reason=reason,
                title=title if isinstance(title, str) else None,
                provider=str(provider) if provider else None,
                language=lang,
                trust_score=trust,
                access_status=access_status,
                content_type=content_type,
                size_bytes=size_bytes,
                keywords_matched=[str(k) for k in keywords],
                meta=dict(c.get("meta") or {}),
            )
        )
    out.sort(key=lambda x: (x.allowed, x.trust_score), reverse=True)
    return out


def default_seed_catalog() -> list[dict[str, Any]]:
    """Curated real agri sources (EN / HI / MR + FAO / USDA / ICAR / Archive)."""
    return [
        # --- Wikipedia EN ---
        {
            "source_url": "https://en.wikipedia.org/wiki/Agriculture",
            "source_type": "wikipedia",
            "license": "cc-by-sa",
            "title": "Agriculture",
            "provider": "Wikipedia",
            "language": "en",
            "trust_score": 80,
        },
        {
            "source_url": "https://en.wikipedia.org/wiki/Crop_rotation",
            "source_type": "wikipedia",
            "license": "cc-by-sa",
            "title": "Crop rotation",
            "provider": "Wikipedia",
            "language": "en",
            "trust_score": 80,
        },
        {
            "source_url": "https://en.wikipedia.org/wiki/Integrated_pest_management",
            "source_type": "wikipedia",
            "license": "cc-by-sa",
            "title": "Integrated pest management",
            "provider": "Wikipedia",
            "language": "en",
            "trust_score": 82,
        },
        {
            "source_url": "https://en.wikipedia.org/wiki/Soil_health",
            "source_type": "wikipedia",
            "license": "cc-by-sa",
            "title": "Soil health",
            "provider": "Wikipedia",
            "language": "en",
            "trust_score": 80,
        },
        {
            "source_url": "https://en.wikipedia.org/wiki/Irrigation",
            "source_type": "wikipedia",
            "license": "cc-by-sa",
            "title": "Irrigation",
            "provider": "Wikipedia",
            "language": "en",
            "trust_score": 80,
        },
        {
            "source_url": "https://en.wikipedia.org/wiki/Organic_farming",
            "source_type": "wikipedia",
            "license": "cc-by-sa",
            "title": "Organic farming",
            "provider": "Wikipedia",
            "language": "en",
            "trust_score": 80,
        },
        {
            "source_url": "https://en.wikipedia.org/wiki/Cotton",
            "source_type": "wikipedia",
            "license": "cc-by-sa",
            "title": "Cotton",
            "provider": "Wikipedia",
            "language": "en",
            "trust_score": 80,
        },
        {
            "source_url": "https://en.wikipedia.org/wiki/Rice",
            "source_type": "wikipedia",
            "license": "cc-by-sa",
            "title": "Rice",
            "provider": "Wikipedia",
            "language": "en",
            "trust_score": 80,
        },
        {
            "source_url": "https://en.wikipedia.org/wiki/Wheat",
            "source_type": "wikipedia",
            "license": "cc-by-sa",
            "title": "Wheat",
            "provider": "Wikipedia",
            "language": "en",
            "trust_score": 80,
        },
        {
            "source_url": "https://en.wikipedia.org/wiki/Sugarcane",
            "source_type": "wikipedia",
            "license": "cc-by-sa",
            "title": "Sugarcane",
            "provider": "Wikipedia",
            "language": "en",
            "trust_score": 80,
        },
        {
            "source_url": "https://en.wikipedia.org/wiki/Fertilizer",
            "source_type": "wikipedia",
            "license": "cc-by-sa",
            "title": "Fertilizer",
            "provider": "Wikipedia",
            "language": "en",
            "trust_score": 80,
        },
        # --- Wikipedia HI ---
        {
            "source_url": "https://hi.wikipedia.org/wiki/कृषि",
            "source_type": "wikipedia",
            "license": "cc-by-sa",
            "title": "कृषि",
            "provider": "Wikipedia",
            "language": "hi",
            "trust_score": 78,
        },
        {
            "source_url": "https://hi.wikipedia.org/wiki/जैविक_खेती",
            "source_type": "wikipedia",
            "license": "cc-by-sa",
            "title": "जैविक खेती",
            "provider": "Wikipedia",
            "language": "hi",
            "trust_score": 78,
        },
        {
            "source_url": "https://hi.wikipedia.org/wiki/सिंचाई",
            "source_type": "wikipedia",
            "license": "cc-by-sa",
            "title": "सिंचाई",
            "provider": "Wikipedia",
            "language": "hi",
            "trust_score": 78,
        },
        # --- Wikipedia MR ---
        {
            "source_url": "https://mr.wikipedia.org/wiki/शेती",
            "source_type": "wikipedia",
            "license": "cc-by-sa",
            "title": "शेती",
            "provider": "Wikipedia",
            "language": "mr",
            "trust_score": 78,
        },
        {
            "source_url": "https://mr.wikipedia.org/wiki/कापूस",
            "source_type": "wikipedia",
            "license": "cc-by-sa",
            "title": "कापूस",
            "provider": "Wikipedia",
            "language": "mr",
            "trust_score": 78,
        },
        {
            "source_url": "https://mr.wikipedia.org/wiki/सिंचन",
            "source_type": "wikipedia",
            "license": "cc-by-sa",
            "title": "सिंचन",
            "provider": "Wikipedia",
            "language": "mr",
            "trust_score": 78,
        },
        # --- FAO ---
        {
            "source_url": (
                "https://www.fao.org/fileadmin/templates/wsfs/docs/expert_paper/"
                "How_to_Feed_the_World_in_2050.pdf"
            ),
            "source_type": "pdf",
            "license": "cc-by",
            "title": "How to Feed the World in 2050 (FAO)",
            "provider": "FAO",
            "language": "en",
            "trust_score": 95,
            "local_cache": "data/source_cache/fao_feed_2050.pdf",
        },
        {
            "source_url": "https://www.fao.org/3/i6583e/i6583e.pdf",
            "source_type": "pdf",
            "license": "cc-by",
            "title": "FAO Soil Organic Carbon",
            "provider": "FAO",
            "language": "en",
            "trust_score": 95,
        },
        {
            "source_url": "https://www.fao.org/3/cb0707en/cb0707en.pdf",
            "source_type": "pdf",
            "license": "cc-by",
            "title": "FAO Crop Production Guide",
            "provider": "FAO",
            "language": "en",
            "trust_score": 95,
        },
        {
            "source_url": "https://en.wikipedia.org/api/rest_v1/page/pdf/Agriculture",
            "source_type": "pdf",
            "license": "cc-by-sa",
            "title": "Agriculture (Wikipedia book PDF)",
            "provider": "Wikipedia",
            "language": "en",
            "trust_score": 80,
            "local_cache": "data/source_cache/wikipedia_agriculture.pdf",
        },
        # --- USDA ---
        {
            "source_url": "https://www.nrcs.usda.gov/conservation-basics/natural-resource-concerns/soils/soil-health",
            "source_type": "web",
            "license": "cc0",
            "title": "USDA NRCS Soil Health",
            "provider": "USDA",
            "language": "en",
            "trust_score": 92,
        },
        {
            "source_url": "https://www.ers.usda.gov/topics/crops/",
            "source_type": "web",
            "license": "cc0",
            "title": "USDA ERS Crops",
            "provider": "USDA",
            "language": "en",
            "trust_score": 90,
        },
        # --- India ---
        {
            "source_url": "https://icar.org.in/",
            "source_type": "web",
            "license": "government_open",
            "title": "Indian Council of Agricultural Research",
            "provider": "ICAR",
            "language": "en",
            "trust_score": 95,
        },
        {
            "source_url": "https://farmer.gov.in/",
            "source_type": "web",
            "license": "government_open",
            "title": "Farmer.gov.in",
            "provider": "India Govt",
            "language": "en",
            "trust_score": 90,
        },
        {
            "source_url": "https://agmarknet.gov.in/",
            "source_type": "web",
            "license": "government_open",
            "title": "Agmarknet Market Prices",
            "provider": "India Govt",
            "language": "en",
            "trust_score": 88,
        },
        {
            "source_url": "https://data.gov.in/catalogs?k=agriculture",
            "source_type": "web",
            "license": "government_open",
            "title": "Data.gov.in Agriculture",
            "provider": "India Govt",
            "language": "en",
            "trust_score": 88,
        },
        # --- Archive classics ---
        {
            "source_url": "https://archive.org/download/cu31924000346686/cu31924000346686.pdf",
            "source_type": "pdf",
            "license": "cc0",
            "title": "Farmers of Forty Centuries (1911)",
            "provider": "Internet Archive",
            "language": "en",
            "trust_score": 85,
        },
        {
            "source_url": "https://archive.org/download/agriculturetextbo00warr/agriculturetextbo00warr.pdf",
            "source_type": "pdf",
            "license": "cc0",
            "title": "Agriculture Textbook (public domain)",
            "provider": "Internet Archive",
            "language": "en",
            "trust_score": 84,
        },
        # --- CGIAR (stable landing pages; avoid 404 deep paths) ---
        {
            "source_url": "https://www.irri.org/",
            "source_type": "web",
            "license": "cc-by",
            "title": "International Rice Research Institute (IRRI)",
            "provider": "CGIAR",
            "language": "en",
            "trust_score": 92,
        },
        {
            "source_url": "https://www.icrisat.org/",
            "source_type": "web",
            "license": "cc-by",
            "title": "ICRISAT",
            "provider": "CGIAR",
            "language": "en",
            "trust_score": 90,
        },
        {
            "source_url": "https://en.wikipedia.org/wiki/Rice",
            "source_type": "wikipedia",
            "license": "cc-by-sa",
            "title": "Rice (stable open knowledge)",
            "provider": "Wikipedia",
            "language": "en",
            "trust_score": 80,
        },
    ]


def real_source_catalog(*, include_heavy: bool = True) -> list[dict[str, Any]]:
    rows = default_seed_catalog()
    if not include_heavy:
        return [r for r in rows if r.get("source_type") != "pdf"]
    return rows
