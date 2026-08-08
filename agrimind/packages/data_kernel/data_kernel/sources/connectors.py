"""Multi-source connectors for Phase 2 data acquisition."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, urlparse

from data_kernel.pipeline.download import download_bytes


@dataclass
class FetchedSource:
    """Normalized fetch result for any source type."""

    source_type: str
    source_url: str
    raw_bytes: bytes
    text: str | None  # None for pure binary (image/audio)
    content_type: str
    checksum: str
    language_hint: str | None = None
    title: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    is_binary: bool = False

    def word_count(self) -> int:
        return len((self.text or "").split())

    def is_valid(self) -> bool:
        if len(self.raw_bytes) < 50:
            return False
        if self.is_binary:
            return True
        return self.text is not None and len(self.text.strip()) > 40


def fetch_source(
    source_url: str,
    source_type: str = "web",
    *,
    inline_content: str | None = None,
    inline_bytes: bytes | None = None,
) -> FetchedSource:
    """
    Fetch and lightly parse by source_type.
    Supports: web, pdf, wikipedia, rss, json, image, audio, structured
    """
    st = (source_type or "web").lower().strip()
    if inline_content is not None:
        data = inline_content.encode("utf-8")
        return FetchedSource(
            source_type=st,
            source_url=source_url,
            raw_bytes=data,
            text=inline_content,
            content_type="text/plain",
            checksum="sha256:" + __import__("hashlib").sha256(data).hexdigest(),
            meta={"mode": "inline"},
        )
    if inline_bytes is not None:
        if st == "pdf" or (
            st not in ("image", "audio")
            and inline_bytes[:4] == b"%PDF"
        ):
            return _pdf_from_bytes(source_url, inline_bytes, meta={"mode": "inline_bytes"})
        return FetchedSource(
            source_type=st,
            source_url=source_url,
            raw_bytes=inline_bytes,
            text=None if st in ("image", "audio") else inline_bytes.decode("utf-8", errors="replace"),
            content_type="application/octet-stream",
            checksum="sha256:" + __import__("hashlib").sha256(inline_bytes).hexdigest(),
            meta={"mode": "inline_bytes"},
            is_binary=st in ("image", "audio"),
        )

    if st == "wikipedia":
        return _fetch_wikipedia(source_url)
    if st == "rss":
        return _fetch_rss(source_url)
    if st == "pdf":
        return _fetch_pdf(source_url)
    if st in ("json", "structured"):
        return _fetch_json_like(source_url, st)
    if st in ("image", "audio"):
        return _fetch_binary(source_url, st)
    # web default
    return _fetch_web(source_url)


def _fetch_web(url: str) -> FetchedSource:
    dl = download_bytes(url)
    text = dl.data.decode("utf-8", errors="replace")
    # strip simple HTML tags if html
    if "html" in dl.content_type.lower() or text.lstrip().lower().startswith("<!doctype") or "<html" in text[:200].lower():
        text = re.sub(r"(?is)<script.*?>.*?</script>", " ", text)
        text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
        text = re.sub(r"(?is)<nav.*?>.*?</nav>", " ", text)
        text = re.sub(r"(?is)<footer.*?>.*?</footer>", " ", text)
        text = re.sub(r"(?is)<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        text = text[:500_000]
    return FetchedSource(
        source_type="web",
        source_url=url,
        raw_bytes=dl.data,
        text=text,
        content_type=dl.content_type,
        checksum=dl.checksum,
        meta={**dl.meta, "attempts": dl.attempts, "status": dl.status, "word_count": len(text.split())},
    )


def _pdf_from_bytes(
    source_url: str,
    data: bytes,
    *,
    content_type: str = "application/pdf",
    meta: dict[str, Any] | None = None,
    max_pages: int = 120,
) -> FetchedSource:
    text = ""
    pages_n = 0
    try:
        from io import BytesIO

        from pypdf import PdfReader

        reader = PdfReader(BytesIO(data))
        parts = []
        for page in reader.pages[:max_pages]:
            t = page.extract_text() or ""
            t = re.sub(r"\s+", " ", t).strip()
            if len(t) > 20:
                parts.append(t)
            pages_n += 1
        text = "\n".join(parts).strip()
    except Exception as exc:
        text = f"[pdf_extract_failed: {exc}]"
    checksum = "sha256:" + __import__("hashlib").sha256(data).hexdigest()
    return FetchedSource(
        source_type="pdf",
        source_url=source_url,
        raw_bytes=data,
        text=text or "[empty_pdf_text]",
        content_type=content_type or "application/pdf",
        checksum=checksum,
        meta={
            **(meta or {}),
            "pages_extracted": pages_n,
            "size_bytes": len(data),
            "word_count": len(text.split()),
        },
    )


def _fetch_pdf(url: str) -> FetchedSource:
    # Agri handbooks / Archive scans: allow large files; if still huge, take first
    # 40MB (allow_partial) so first pages can still be curated instead of hard-fail.
    max_full = 100_000_000
    max_partial = 40_000_000
    try:
        dl = download_bytes(
            url,
            max_bytes=max_full,
            timeout=90,
            retries=2,
            allow_partial=False,
        )
    except RuntimeError as exc:
        if "payload_exceeds_size_limit" not in str(exc):
            raise
        dl = download_bytes(
            url,
            max_bytes=max_partial,
            timeout=90,
            retries=1,
            allow_partial=True,
        )
    fetched = _pdf_from_bytes(
        url,
        dl.data,
        content_type=dl.content_type or "application/pdf",
        meta={
            **dl.meta,
            "attempts": dl.attempts,
            "mode": "http",
            "final_url": dl.url,
        },
    )
    # If partial bytes yielded no useful text, surface a clear size error
    if dl.meta.get("partial") and (
        not fetched.text
        or fetched.text.startswith("[pdf_extract_failed")
        or fetched.text.startswith("[empty_pdf")
        or fetched.word_count() < 40
    ):
        raise RuntimeError(
            f"download_failed: payload_exceeds_size_limit:partial_extract_failed "
            f"bytes={len(dl.data)}"
        )
    return fetched


def _fetch_wikipedia(url_or_title: str) -> FetchedSource:
    """Accept full wiki URL or bare title; fetch extract via MediaWiki API.

    Supports English, Hindi, and Marathi (Devanagari titles preserved).
    """
    title = url_or_title
    lang = "en"
    parsed = urlparse(url_or_title)
    if parsed.netloc:
        # https://en.wikipedia.org/wiki/Crop_rotation  or hi/mr
        m = re.match(r"([a-z]{2})\.wikipedia\.org", parsed.netloc)
        if m:
            lang = m.group(1)
        if "/wiki/" in parsed.path:
            title = parsed.path.split("/wiki/", 1)[1]
    # Keep Devanagari; only convert underscores
    title = title.replace("_", " ").strip()
    api = (
        f"https://{lang}.wikipedia.org/w/api.php?action=query"
        f"&prop=extracts|info&inprop=url&explaintext=1&format=json"
        f"&titles={quote(title)}"
    )
    try:
        dl = download_bytes(api)
        data = json.loads(dl.data.decode("utf-8", errors="replace"))
        pages = (data.get("query") or {}).get("pages") or {}
        extract = ""
        page_title = title
        full_url = f"https://{lang}.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"
        for _pid, page in pages.items():
            extract = page.get("extract") or ""
            page_title = page.get("title") or title
            full_url = page.get("fullurl") or full_url
            break
        text = extract or f"[wikipedia_empty:{title}]"
        raw = text.encode("utf-8")
        return FetchedSource(
            source_type="wikipedia",
            source_url=url_or_title,
            raw_bytes=raw,
            text=text,
            content_type="application/json",
            checksum="sha256:" + __import__("hashlib").sha256(raw).hexdigest(),
            language_hint=lang if lang in ("en", "hi", "mr") else None,
            title=page_title,
            meta={
                "api": api,
                "lang": lang,
                "full_url": full_url,
                "word_count": len(text.split()),
            },
        )
    except Exception as exc:
        raw = f"[wikipedia_fetch_failed: {exc}]".encode("utf-8")
        return FetchedSource(
            source_type="wikipedia",
            source_url=url_or_title,
            raw_bytes=raw,
            text=raw.decode("utf-8"),
            content_type="text/plain",
            checksum="sha256:" + __import__("hashlib").sha256(raw).hexdigest(),
            language_hint=lang if lang in ("en", "hi", "mr") else None,
            meta={"error": str(exc), "lang": lang},
        )


def _fetch_rss(url: str) -> FetchedSource:
    dl = download_bytes(url)
    text_parts: list[str] = []
    try:
        import feedparser

        feed = feedparser.parse(dl.data)
        for e in (feed.entries or [])[:30]:
            title = getattr(e, "title", "") or ""
            summary = getattr(e, "summary", "") or getattr(e, "description", "") or ""
            text_parts.append(f"{title}\n{summary}")
        title = getattr(feed.feed, "title", None)
    except Exception as exc:
        text_parts = [dl.data.decode("utf-8", errors="replace")[:5000]]
        title = None
        meta_err = str(exc)
    else:
        meta_err = None
    text = "\n\n".join(text_parts) or "[empty_rss]"
    return FetchedSource(
        source_type="rss",
        source_url=url,
        raw_bytes=dl.data,
        text=text,
        content_type=dl.content_type,
        checksum=dl.checksum,
        title=title,
        meta={"entries": len(text_parts), "parse_error": meta_err, **dl.meta},
    )


def _fetch_json_like(url: str, source_type: str) -> FetchedSource:
    dl = download_bytes(url)
    try:
        obj = json.loads(dl.data.decode("utf-8", errors="replace"))
        text = json.dumps(obj, ensure_ascii=False, indent=2)[:200_000]
    except Exception:
        text = dl.data.decode("utf-8", errors="replace")
    return FetchedSource(
        source_type=source_type,
        source_url=url,
        raw_bytes=dl.data,
        text=text,
        content_type=dl.content_type or "application/json",
        checksum=dl.checksum,
        meta=dl.meta,
    )


def _fetch_binary(url: str, source_type: str) -> FetchedSource:
    dl = download_bytes(url, max_bytes=20_000_000)
    return FetchedSource(
        source_type=source_type,
        source_url=url,
        raw_bytes=dl.data,
        text=None,
        content_type=dl.content_type,
        checksum=dl.checksum,
        meta={**dl.meta, "size": len(dl.data)},
        is_binary=True,
    )
