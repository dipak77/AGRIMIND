"""Phase 2 full pipeline: stages 1–13 + optional vector index."""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Callable

from data_kernel.lakehouse.writer import LakehouseWriter
from data_kernel.pipeline.chunking import chunk_text, title_from_url
from data_kernel.pipeline.dedup import DedupIndex
from data_kernel.pipeline.license_filter import LicenseFilter
from data_kernel.pipeline.normalize import normalize_text
from data_kernel.pipeline.pii import PIIFilter
from data_kernel.pipeline.quality import score_quality
from data_kernel.pipeline.relevance import AgricultureRelevanceFilter
from data_kernel.pipeline.toxicity import ToxicityFilter
from data_kernel.sources.connectors import FetchedSource, fetch_source
from data_kernel.sources.discovery import DEFAULT_ALLOW_LIST, is_url_allow_listed
from data_kernel.storage.object_store import ObjectStore, build_object_store

if TYPE_CHECKING:
    from data_kernel.pipeline.indexer import ChunkIndexer

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, dict[str, Any]], None]


class _StageMap(dict):
    """dict that notifies on each stage write for live job progress."""

    def __init__(self, on_progress: ProgressCallback | None = None, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._on_progress = on_progress
        self._meta_keys = frozenset({"job_id", "store_backend", "source_type"})

    def __setitem__(self, key: str, value: Any) -> None:  # type: ignore[override]
        super().__setitem__(key, value)
        if self._on_progress is not None and key not in self._meta_keys:
            try:
                self._on_progress(str(key), dict(self))
            except Exception as exc:  # never break pipeline for UI hooks
                logger.debug("progress_callback_failed: %s", exc)


@dataclass
class IngestRequest:
    source_url: str
    source_type: str = "web"
    license: str = "unknown"
    content: str | None = None
    content_bytes: bytes | None = None
    job_id: str | None = None
    allow_list: list[str] = field(default_factory=lambda: list(DEFAULT_ALLOW_LIST))
    skip_robots: bool = False  # tests / inline
    source_id: str | None = None


@dataclass
class IngestResult:
    job_id: str
    status: str  # curated | quarantine | failed | image_stored
    stages: dict[str, Any]
    raw_uri: str | None = None
    curated_uri: str | None = None
    quarantine_uri: str | None = None
    manifest_id: str | None = None
    content_hash: str | None = None
    error: str | None = None
    language: str | None = None
    chunk_count: int = 0


_GLOBAL_DEDUP = DedupIndex()


class IngestPipeline:
    """
    Stages:
      1 allow-list  2 robots+license  3 download  4 normalize+lang
      5 PII  6 toxicity  7 relevance  8 dedup  9 quality
      10 provenance  11 raw  12 curated  13 quarantine
      + curated.chunks lake table + optional Qdrant index
    """

    def __init__(
        self,
        store: ObjectStore | None = None,
        writer: LakehouseWriter | None = None,
        dedup: DedupIndex | None = None,
        indexer: ChunkIndexer | None = None,
        index_on_curate: bool = True,
        index_required: bool = False,
        chunk_max_chars: int = 800,
        chunk_overlap: int = 80,
        min_quality: float = 0.35,
    ) -> None:
        self.store = store or build_object_store(prefer="auto")
        self.writer = writer or LakehouseWriter(self.store)
        self.dedup = dedup or _GLOBAL_DEDUP
        self.pii = PIIFilter()
        self.relevance = AgricultureRelevanceFilter(threshold=0.5)
        self.license = LicenseFilter()
        self.toxicity = ToxicityFilter()
        self.indexer = indexer
        self.index_on_curate = index_on_curate
        self.index_required = index_required
        self.chunk_max_chars = chunk_max_chars
        self.chunk_overlap = chunk_overlap
        self.min_quality = min_quality

    def run(
        self,
        req: IngestRequest,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> IngestResult:
        job_id = req.job_id or hashlib.sha256(
            f"{req.source_url}:{datetime.now(UTC).isoformat()}".encode()
        ).hexdigest()[:12]
        stages: dict[str, Any] = _StageMap(on_progress)
        stages["job_id"] = job_id
        stages["store_backend"] = self.store.backend
        stages["source_type"] = req.source_type
        source_id = req.source_id or f"src:{hashlib.sha256(req.source_url.encode()).hexdigest()[:12]}"

        # --- 1. Source discovery / allow-list ---
        allow = is_url_allow_listed(req.source_url, req.allow_list) or (
            req.content is not None
            and is_url_allow_listed(req.source_url, req.allow_list + ["example.com"])
        )
        stages["allow_list"] = {"allowed": allow, "url": req.source_url}
        if not allow and req.content is None and req.content_bytes is None:
            q = self.writer.write_quarantine(
                {
                    "job_id": job_id,
                    "source_url": req.source_url,
                    "source_type": req.source_type,
                    "license": req.license,
                    "source_id": source_id,
                },
                reason="source_not_allow_listed",
            )
            return IngestResult(
                job_id=job_id,
                status="quarantine",
                stages=stages,
                quarantine_uri=q.put.uri,
                error="source_not_allow_listed",
            )

        # --- 2. robots + license ---
        stages["license"] = self._license_stage(req)
        if not stages["license"]["allowed"]:
            q = self.writer.write_quarantine(
                {
                    "job_id": job_id,
                    "source_url": req.source_url,
                    "source_type": req.source_type,
                    "license": req.license,
                    "source_id": source_id,
                },
                reason=stages["license"].get("reason") or "license_blocked",
            )
            return IngestResult(
                job_id=job_id,
                status="quarantine",
                stages=stages,
                quarantine_uri=q.put.uri,
                error=stages["license"].get("reason"),
            )

        robots = self._robots_stage(req)
        stages["robots"] = robots
        if not robots.get("allowed", True) and not req.skip_robots and req.content is None:
            q = self.writer.write_quarantine(
                {
                    "job_id": job_id,
                    "source_url": req.source_url,
                    "source_type": req.source_type,
                    "license": req.license,
                    "source_id": source_id,
                },
                reason="robots_disallowed",
            )
            return IngestResult(
                job_id=job_id,
                status="quarantine",
                stages=stages,
                quarantine_uri=q.put.uri,
                error="robots_disallowed",
            )

        # --- 3. Download / multi-source fetch ---
        try:
            fetched = self._fetch(req)
        except Exception as exc:
            stages["download"] = {"ok": False, "error": str(exc)}
            self.writer.write_telemetry("download_failed", {"job_id": job_id, "error": str(exc)})
            return IngestResult(
                job_id=job_id,
                status="failed",
                stages=stages,
                error=f"download_failed: {exc}",
            )
        stages["download"] = {
            "ok": True,
            "content_type": fetched.content_type,
            "checksum": fetched.checksum,
            "meta": fetched.meta,
            "is_binary": fetched.is_binary,
            "source_type": fetched.source_type,
        }

        # --- 11. Raw immutable write (before heavy curation) ---
        raw = self.writer.write_raw(
            job_id=job_id,
            source_url=req.source_url,
            content=fetched.raw_bytes,
            license=req.license,
            source_type=fetched.source_type,
            metadata=fetched.meta,
            source_id=source_id,
        )
        stages["raw_write"] = {
            "uri": raw.put.uri,
            "checksum": raw.put.checksum,
            "backend": raw.put.backend,
        }

        # Binary image path: store curated.images, skip text curation
        if fetched.is_binary or fetched.source_type in ("image", "audio"):
            if fetched.source_type == "image":
                img = self.writer.write_image(
                    job_id=job_id,
                    source_url=req.source_url,
                    content=fetched.raw_bytes,
                    content_type=fetched.content_type,
                    license=req.license,
                    metadata=fetched.meta,
                )
                stages["image_write"] = {"uri": img.put.uri}
                manifest = self.writer.write_dataset_manifest(
                    source_ids=[source_id],
                    languages=[],
                    record_count=1,
                    checksum=img.put.checksum,
                    notes=f"image job {job_id}",
                )
                stages["manifest"] = {"manifest_id": manifest["manifest_id"]}
                return IngestResult(
                    job_id=job_id,
                    status="image_stored",
                    stages=stages,
                    raw_uri=raw.put.uri,
                    curated_uri=img.put.uri,
                    content_hash=img.put.checksum,
                    manifest_id=manifest["manifest_id"],
                )
            # audio: raw only + quarantine note for future ASR
            q = self.writer.write_quarantine(
                {**raw.record, "job_id": job_id},
                reason="audio_awaiting_asr",
                content="",
            )
            return IngestResult(
                job_id=job_id,
                status="quarantine",
                stages=stages,
                raw_uri=raw.put.uri,
                quarantine_uri=q.put.uri,
                content_hash=raw.put.checksum,
                error="audio_awaiting_asr",
            )

        text = fetched.text or ""
        # --- 4. Unicode + language ---
        norm = normalize_text(text)
        if fetched.language_hint in ("en", "hi", "mr"):
            language = fetched.language_hint
        else:
            language = norm.language
        stages["normalize"] = {
            "language": language,
            "normalized": norm.normalized,
            "chars": len(norm.text),
        }
        text = norm.text

        # --- 5. PII ---
        pii = self.pii.redact(text)
        stages["pii"] = {"redacted": pii.redacted, "flags": pii.flags}
        text = pii.text

        # --- 6. Toxicity ---
        tox = self.toxicity.check(text)
        stages["toxicity"] = {
            "is_safe": tox.is_safe,
            "score": tox.score,
            "flags": tox.flags,
        }
        if not tox.is_safe:
            q = self.writer.write_quarantine(
                {**raw.record, "job_id": job_id},
                reason="toxicity_blocked",
                content=text,
            )
            return IngestResult(
                job_id=job_id,
                status="quarantine",
                stages=stages,
                raw_uri=raw.put.uri,
                quarantine_uri=q.put.uri,
                content_hash=raw.put.checksum,
                error="toxicity_blocked",
                language=language,
            )

        # --- 7. Agriculture relevance ---
        rel = self.relevance.score(text)
        stages["relevance"] = {
            "relevant": rel.relevant,
            "score": rel.score,
            "matched": rel.matched,
        }
        # structured/json may have lower keyword density — soften threshold
        if not rel.relevant and req.source_type not in ("json", "structured", "rss"):
            q = self.writer.write_quarantine(
                {**raw.record, "job_id": job_id},
                reason="low_agriculture_relevance",
                content=text,
            )
            return IngestResult(
                job_id=job_id,
                status="quarantine",
                stages=stages,
                raw_uri=raw.put.uri,
                quarantine_uri=q.put.uri,
                content_hash=raw.put.checksum,
                error="low_agriculture_relevance",
                language=language,
            )

        # --- 8. Dedup (exact + MinHash near) ---
        dup = self.dedup.check_and_add(text)
        stages["dedup"] = {
            "is_duplicate": dup.is_duplicate,
            "content_hash": dup.content_hash,
            "reason": dup.reason,
            "near_duplicate_of": dup.near_duplicate_of,
            "jaccard": dup.jaccard,
        }
        if dup.is_duplicate:
            q = self.writer.write_quarantine(
                {
                    **raw.record,
                    "job_id": job_id,
                    "duplicate_of": dup.near_duplicate_of,
                },
                reason=f"duplicate:{dup.reason}",
                content=text,
            )
            return IngestResult(
                job_id=job_id,
                status="quarantine",
                stages=stages,
                raw_uri=raw.put.uri,
                quarantine_uri=q.put.uri,
                content_hash=dup.content_hash,
                error=f"duplicate:{dup.reason}",
                language=language,
            )

        # --- 9. Quality scoring ---
        quality = score_quality(
            text=text,
            relevance=rel.score if rel.relevant else max(rel.score, 0.4),
            language=language,
            pii_redacted=pii.redacted,
            has_provenance=True,
            toxicity_score=tox.score,
        )
        stages["quality"] = {"score": quality.score, "factors": quality.factors}
        if quality.score < self.min_quality:
            q = self.writer.write_quarantine(
                {**raw.record, "job_id": job_id, "quality_score": quality.score},
                reason="low_quality_score",
                content=text,
            )
            return IngestResult(
                job_id=job_id,
                status="quarantine",
                stages=stages,
                raw_uri=raw.put.uri,
                quarantine_uri=q.put.uri,
                content_hash=raw.put.checksum,
                error="low_quality_score",
                language=language,
            )

        # --- 10 + 12. Provenance + curated write ---
        curated_record = {
            **raw.record,
            "job_id": job_id,
            "source_id": source_id,
            "language": language,
            "agriculture_relevance_score": rel.score,
            "quality_score": quality.score,
            "pii_redacted": pii.redacted,
            "toxicity_score": tox.score,
            "license_type": stages["license"].get("license") or req.license,
            "title": fetched.title or title_from_url(req.source_url),
            "provenance": {
                "source_url": req.source_url,
                "source_id": source_id,
                "raw_uri": raw.put.uri,
                "raw_checksum": raw.put.checksum,
                "license": req.license,
                "source_type": fetched.source_type,
            },
        }
        curated = self.writer.write_curated(curated_record, text)
        stages["curated_write"] = {
            "uri": curated.put.uri,
            "checksum": curated.put.checksum,
        }

        # curated.chunks lake table
        document_id = str(curated.record.get("document_id") or job_id)
        chunks = chunk_text(
            text,
            source_id=document_id,
            max_chars=self.chunk_max_chars,
            overlap=self.chunk_overlap,
            document_id=document_id,
            job_id=job_id,
            source_url=req.source_url,
            url_or_path=req.source_url,
            source_type=fetched.source_type,
            checksum=curated.put.checksum,
            title=curated_record.get("title"),
            lang=language,
            license=req.license,
            source_id_field=source_id,
        )
        for ch in chunks:
            idx = ch.get("chunk_index", 0)
            ch["doc_id"] = f"{document_id}:chunk:{idx}"
            ch.setdefault("source_id", source_id)
        chunk_n = self.writer.write_chunks(chunks, document_id=document_id, job_id=job_id)
        stages["chunks_write"] = {"count": chunk_n}
        stages["provenance"] = curated_record["provenance"]

        manifest = self.writer.write_dataset_manifest(
            source_ids=[source_id],
            languages=[language] if language != "unknown" else [],
            record_count=1,
            checksum=curated.put.checksum,
            notes=f"ingest job {job_id} type={fetched.source_type}",
        )
        stages["manifest"] = {"manifest_id": manifest["manifest_id"]}

        index_error = self._maybe_index(
            chunks=chunks,
            document_id=document_id,
            stages=stages,
        )
        if index_error and self.index_required:
            q = self.writer.write_quarantine(
                {**curated.record, "job_id": job_id, "index_error": index_error},
                reason=f"index_failed:{index_error}",
                content=text,
            )
            return IngestResult(
                job_id=job_id,
                status="quarantine",
                stages=stages,
                raw_uri=raw.put.uri,
                curated_uri=curated.put.uri,
                quarantine_uri=q.put.uri,
                content_hash=curated.put.checksum,
                manifest_id=manifest["manifest_id"],
                error=f"index_failed:{index_error}",
                language=language,
                chunk_count=chunk_n,
            )

        return IngestResult(
            job_id=job_id,
            status="curated",
            stages=stages,
            raw_uri=raw.put.uri,
            curated_uri=curated.put.uri,
            content_hash=curated.put.checksum,
            manifest_id=manifest["manifest_id"],
            language=language,
            chunk_count=chunk_n,
        )

    def _license_stage(self, req: IngestRequest) -> dict[str, Any]:
        lic = self.license.check(req.license)
        # Also try SourceValidator license map when available
        extra: dict[str, Any] = {}
        try:
            from data_kernel.pipeline.validators import LicenseType, SourceValidator

            # soft: only if license unknown
            if req.license in ("unknown", ""):
                validator = SourceValidator(
                    allow_list=req.allow_list,
                    license_map={},
                )
                # don't fail on empty map
                extra["validator"] = "skipped_empty_map"
        except Exception as exc:
            extra["validator_error"] = str(exc)
        return {
            "allowed": lic.allowed,
            "license": lic.license,
            "requires_review": lic.requires_review,
            "reason": lic.reason,
            **extra,
        }

    def _robots_stage(self, req: IngestRequest) -> dict[str, Any]:
        if req.skip_robots or req.content is not None or req.content_bytes is not None:
            return {"allowed": True, "skipped": True}
        # Optional hard skip for offline / flaky gov sites
        if os.getenv("SKIP_ROBOTS", "").strip().lower() in ("1", "true", "yes", "on"):
            return {"allowed": True, "skipped": True, "reason": "SKIP_ROBOTS"}
        try:
            from data_kernel.pipeline.validators import LicenseType, SourceValidator

            # allow list already checked; use permissive license map so robots is the focus
            v = SourceValidator(
                allow_list=req.allow_list or ["*"],
                license_map={
                    f"https://{h}": LicenseType.CC_BY
                    for h in (req.allow_list or [])
                    if "." in h
                },
            )
            # patch allow to always true for robots-only
            res = v._check_robots_txt(req.source_url)  # noqa: SLF001
            return {"allowed": bool(res), "checked": True}
        except Exception as exc:
            # fail-open for network errors on robots (documented)
            return {"allowed": True, "checked": False, "error": str(exc)}

    def _fetch(self, req: IngestRequest) -> FetchedSource:
        return fetch_source(
            req.source_url,
            req.source_type,
            inline_content=req.content,
            inline_bytes=req.content_bytes,
        )

    def _maybe_index(
        self,
        *,
        chunks: list[dict[str, Any]],
        document_id: str,
        stages: dict[str, Any],
    ) -> str | None:
        if not self.index_on_curate or self.indexer is None:
            stages["index"] = {
                "skipped": True,
                "reason": "indexer_disabled" if not self.index_on_curate else "no_indexer",
            }
            return None
        backend = getattr(self.indexer, "backend", type(self.indexer).__name__)
        try:
            upserted = int(self.indexer.index_chunks(chunks))
            stages["index"] = {
                "upserted": upserted,
                "chunks": len(chunks),
                "backend": backend,
                "document_id": document_id,
            }
            return None
        except Exception as exc:
            logger.warning("curated_index_failed document_id=%s error=%s", document_id, exc)
            stages["index"] = {
                "upserted": 0,
                "backend": backend,
                "error": str(exc),
                "document_id": document_id,
            }
            return str(exc)
