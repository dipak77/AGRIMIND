"""Download with size limit, retry, and checksum (Phase 2 stage 3)."""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote, urlparse


DEFAULT_MAX_BYTES = 5_000_000
DEFAULT_RETRIES = 3
DEFAULT_TIMEOUT = 30


@dataclass
class DownloadResult:
    data: bytes
    content_type: str
    checksum: str
    status: int
    attempts: int
    url: str
    meta: dict[str, Any]


def download_bytes(
    url: str,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    retries: int = DEFAULT_RETRIES,
    timeout: float = DEFAULT_TIMEOUT,
    user_agent: str = "AgrimindBot/1.0 (+https://agrimind.local; agri open-knowledge)",
    allow_partial: bool = False,
) -> DownloadResult:
    """
    Download URL into memory (capped).

    If allow_partial=True and the body exceeds max_bytes, return the first
    max_bytes with meta.partial=True instead of failing (used for large PDFs
    so first pages can still be extracted).
    """
    # Resolve Archive.org identifiers to a real PDF file when possible
    resolved = resolve_archive_pdf_url(url, max_bytes=max_bytes, timeout=min(timeout, 15))
    if resolved:
        url = resolved["url"]
        # Prefer known size when available
        if resolved.get("size") and int(resolved["size"]) > max_bytes and not allow_partial:
            raise RuntimeError(
                f"download_failed: payload_exceeds_size_limit:"
                f"{resolved['size']}>{max_bytes} (archive metadata)"
            )

    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": user_agent,
                    "Accept": "*/*",
                },
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                status = getattr(resp, "status", 200) or 200
                ctype = resp.headers.get("Content-Type", "application/octet-stream")
                data = resp.read(max_bytes + 1)
            partial = False
            if len(data) > max_bytes:
                if allow_partial:
                    data = data[:max_bytes]
                    partial = True
                else:
                    raise ValueError(
                        f"payload_exceeds_size_limit:{len(data)}>{max_bytes}"
                    )
            checksum = "sha256:" + hashlib.sha256(data).hexdigest()
            return DownloadResult(
                data=data,
                content_type=ctype,
                checksum=checksum,
                status=int(status),
                attempts=attempt,
                url=url,
                meta={
                    "ok": True,
                    "mode": "http",
                    "bytes": len(data),
                    "partial": partial,
                    "resolved_from_archive": bool(resolved),
                },
            )
        except urllib.error.HTTPError as exc:
            last_err = exc
            # Do not retry permanent client errors
            if exc.code in (400, 401, 403, 404, 410, 451):
                break
            if attempt < retries:
                time.sleep(0.4 * attempt)
            continue
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            last_err = exc
            # size limit is permanent for this request
            if isinstance(exc, ValueError) and "payload_exceeds_size_limit" in str(exc):
                break
            if attempt < retries:
                time.sleep(0.4 * attempt)
            continue
    raise RuntimeError(f"download_failed after {retries} attempts: {last_err}")


def resolve_archive_pdf_url(
    url: str,
    *,
    max_bytes: int = 80_000_000,
    timeout: float = 15.0,
) -> dict[str, Any] | None:
    """
    Map https://archive.org/download/{id}/{maybe_wrong}.pdf
    → best actual PDF file from item metadata (under size cap when possible).
    """
    try:
        parsed = urlparse(url)
        host = (parsed.netloc or "").lower()
        if "archive.org" not in host:
            return None
        m = re.match(r"^/download/([^/]+)(?:/([^?]+))?", parsed.path or "")
        if not m:
            return None
        ident = unquote(m.group(1))
        meta_url = f"https://archive.org/metadata/{ident}"
        req = urllib.request.Request(
            meta_url,
            headers={"User-Agent": "AgrimindBot/1.0 (+https://agrimind.local)"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            raw = resp.read(2_000_000)
        meta = json.loads(raw.decode("utf-8", errors="replace"))
        files = meta.get("files") or []
        pdfs: list[dict[str, Any]] = []
        for f in files:
            name = str(f.get("name") or "")
            fmt = str(f.get("format") or "").lower()
            if not name.lower().endswith(".pdf") and "pdf" not in fmt:
                continue
            # skip derivatives / text dumps that aren't primary
            if name.lower().endswith("_text.pdf"):
                continue
            try:
                size = int(f.get("size") or 0)
            except Exception:
                size = 0
            pdfs.append({"name": name, "size": size})
        if not pdfs:
            return None
        # Prefer largest under cap, else smallest overall (partial extract)
        under = [p for p in pdfs if 0 < p["size"] <= max_bytes]
        if under:
            best = sorted(under, key=lambda p: p["size"], reverse=True)[0]
        else:
            # pick smallest non-zero PDF for partial download
            nonzero = [p for p in pdfs if p["size"] > 0]
            best = sorted(nonzero or pdfs, key=lambda p: p["size"] or 10**18)[0]
        file_url = f"https://archive.org/download/{ident}/{best['name'].replace(' ', '%20')}"
        return {"url": file_url, "size": best["size"], "name": best["name"], "identifier": ident}
    except Exception:
        return None
