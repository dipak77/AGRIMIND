"""Simple text chunker for curated documents → vector index."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse


_PARA_SPLIT = re.compile(r"\n\s*\n+")


def title_from_url(url: str) -> str:
    """Best-effort title from a source URL path segment."""
    if not url:
        return ""
    try:
        path = urlparse(url).path or ""
        seg = path.rstrip("/").split("/")[-1] if path else ""
        if not seg:
            host = urlparse(url).netloc or url
            return host
        if "." in seg and not seg.startswith("."):
            seg = seg.rsplit(".", 1)[0]
        return seg.replace("-", " ").replace("_", " ").strip() or url
    except Exception:
        return url


def chunk_text(
    text: str,
    *,
    source_id: str = "",
    max_chars: int = 800,
    overlap: int = 80,
    **extra: Any,
) -> list[dict[str, Any]]:
    """
    Split text into overlapping chunks of ~max_chars.

    Prefer paragraph boundaries; fall back to hard splits when a paragraph
    exceeds max_chars. Returns list of dicts with at least:
      text, chunk_index, source_id, plus any **extra provenance fields.
    """
    if not text or not str(text).strip():
        return []

    max_chars = max(64, int(max_chars))
    overlap = max(0, min(int(overlap), max_chars // 2))

    normalized = str(text).replace("\r\n", "\n").replace("\r", "\n").strip()
    paragraphs = [p.strip() for p in _PARA_SPLIT.split(normalized) if p.strip()]
    if not paragraphs:
        paragraphs = [normalized]

    # Flatten into max_chars-sized segments first
    segments: list[str] = []
    for para in paragraphs:
        if len(para) <= max_chars:
            segments.append(para)
        else:
            segments.extend(_hard_split(para, max_chars=max_chars, overlap=overlap))

    # Pack consecutive small segments into larger chunks up to max_chars
    packed: list[str] = []
    buf = ""
    for seg in segments:
        if not buf:
            buf = seg
            continue
        candidate = f"{buf}\n\n{seg}"
        if len(candidate) <= max_chars:
            buf = candidate
        else:
            packed.append(buf)
            if overlap > 0 and len(buf) > overlap:
                tail = buf[-overlap:].lstrip()
                # avoid re-attaching full previous if overlap is just whitespace
                buf = f"{tail}\n\n{seg}".strip() if tail else seg
                if len(buf) > max_chars:
                    # drop tail and start clean with seg (already sized)
                    packed_extra = _hard_split(buf, max_chars=max_chars, overlap=overlap)
                    packed.extend(packed_extra[:-1])
                    buf = packed_extra[-1] if packed_extra else seg
            else:
                buf = seg
    if buf:
        packed.append(buf)

    chunks: list[dict[str, Any]] = []
    for i, body in enumerate(packed):
        body = body.strip()
        if not body:
            continue
        doc: dict[str, Any] = {
            "text": body,
            "content": body,
            "chunk_index": i,
            "source_id": source_id,
            "excerpt": body[:500],
        }
        for k, v in extra.items():
            if k not in doc and v is not None:
                doc[k] = v
        chunks.append(doc)
    return chunks


def _hard_split(text: str, *, max_chars: int, overlap: int) -> list[str]:
    """Character windows with overlap when no good boundary exists."""
    if len(text) <= max_chars:
        return [text]
    parts: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(n, start + max_chars)
        if end < n:
            window = text[start:end]
            sp = window.rfind(" ")
            if sp > max_chars // 2:
                end = start + sp
        piece = text[start:end].strip()
        if piece:
            parts.append(piece)
        if end >= n:
            break
        next_start = end - overlap if overlap else end
        start = max(next_start, start + 1)
    return parts
