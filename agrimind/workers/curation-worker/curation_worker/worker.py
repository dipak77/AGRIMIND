"""Temporal Phase 2 workflows: Ingest → Curation → Index (+ type helpers)."""

from __future__ import annotations

import asyncio
import os
from datetime import timedelta
from typing import Any

import structlog
from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.worker import Worker

logger = structlog.get_logger()


def _store_and_writer():
    from data_kernel.lakehouse.writer import LakehouseWriter
    from data_kernel.storage.object_store import build_object_store

    store = build_object_store(
        minio_endpoint=os.getenv("MINIO_ENDPOINT", "http://localhost:9000"),
        minio_access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
        minio_secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
        local_root=os.getenv("LAKEHOUSE_ROOT", "./data/lakehouse"),
        prefer=os.getenv("OBJECT_STORE", "auto"),
    )
    writer = LakehouseWriter(store)
    return store, writer


def _build_indexer() -> Any | None:
    if os.getenv("INDEX_ON_INGEST", "true").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return None
    try:
        from memory.indexing.curated_indexer import build_default_indexer

        return build_default_indexer(
            qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333"),
            collection=os.getenv("QDRANT_COLLECTION", "agrimind_chunks"),
            prefer_in_memory=os.getenv("INDEX_PREFER_IN_MEMORY", "").lower()
            in ("1", "true", "yes"),
        )
    except Exception as exc:
        logger.warning("curated_indexer_unavailable", error=str(exc))
        return None


# --- Activities ---


@activity.defn
async def ingest_source_activity(payload: dict[str, Any]) -> dict[str, Any]:
    """Download/fetch + raw write only (IngestWorkflow)."""
    from data_kernel.sources.connectors import fetch_source
    from data_kernel.sources.discovery import is_url_allow_listed

    store, writer = _store_and_writer()
    url = payload["source_url"]
    st = payload.get("source_type", "web")
    lic = payload.get("license", "unknown")
    job_id = payload.get("job_id") or "unknown"
    allow = payload.get("allow_list")

    if not is_url_allow_listed(url, allow) and not payload.get("content"):
        return {"ok": False, "stage": "ingest", "error": "source_not_allow_listed", "job_id": job_id}

    try:
        fetched = fetch_source(
            url,
            st,
            inline_content=payload.get("content"),
            inline_bytes=None,
        )
        raw = writer.write_raw(
            job_id=job_id,
            source_url=url,
            content=fetched.raw_bytes,
            license=lic,
            source_type=fetched.source_type,
            metadata=fetched.meta,
        )
        # stash text for next stage (small enough for Temporal payload in dev)
        text = fetched.text
        if text and len(text) > 400_000:
            text = text[:400_000]
        return {
            "ok": True,
            "stage": "ingest",
            "job_id": job_id,
            "raw_uri": raw.put.uri,
            "raw_checksum": raw.put.checksum,
            "raw_record": raw.record,
            "text": text,
            "is_binary": fetched.is_binary,
            "source_type": fetched.source_type,
            "content_type": fetched.content_type,
            "language_hint": fetched.language_hint,
            "title": fetched.title,
        }
    except Exception as exc:
        writer.write_telemetry("ingest_activity_failed", {"job_id": job_id, "error": str(exc)})
        return {"ok": False, "stage": "ingest", "error": str(exc), "job_id": job_id}


@activity.defn
async def curation_filter_activity(payload: dict[str, Any]) -> dict[str, Any]:
    """Full curation filters + curated write + chunks table (CurationWorkflow)."""
    from data_kernel.pipeline.ingest_pipeline import IngestPipeline, IngestRequest

    store, writer = _store_and_writer()
    # Re-run full pipeline with inline content when text present (idempotent curate path)
    text = payload.get("text")
    if not text and not payload.get("is_binary"):
        return {"ok": False, "stage": "curation", "error": "no_text_for_curation"}

    pipeline = IngestPipeline(
        store=store,
        writer=writer,
        indexer=None,
        index_on_curate=False,
    )
    req = IngestRequest(
        source_url=payload.get("source_url") or payload.get("raw_record", {}).get("source_url", ""),
        source_type=payload.get("source_type", "web"),
        license=payload.get("license", "unknown"),
        content=text,
        job_id=payload.get("job_id"),
        skip_robots=True,  # already checked in ingest
        allow_list=payload.get("allow_list"),
    )
    # If binary image path
    if payload.get("is_binary") and payload.get("source_type") == "image":
        # raw already written; pipeline with bytes
        return {
            "ok": True,
            "stage": "curation",
            "status": "image_raw_only",
            "job_id": payload.get("job_id"),
            "raw_uri": payload.get("raw_uri"),
        }

    result = pipeline.run(req)
    return {
        "ok": result.status in ("curated", "image_stored"),
        "stage": "curation",
        "status": result.status,
        "job_id": result.job_id,
        "stages": result.stages,
        "raw_uri": result.raw_uri or payload.get("raw_uri"),
        "curated_uri": result.curated_uri,
        "quarantine_uri": result.quarantine_uri,
        "manifest_id": result.manifest_id,
        "content_hash": result.content_hash,
        "language": result.language,
        "chunk_count": result.chunk_count,
        "error": result.error,
        "text": text if result.status == "curated" else None,
        "document_id": (result.stages.get("index") or {}).get("document_id")
        or (result.stages.get("chunks_write") and result.stages.get("curated_write")),
        "source_url": req.source_url,
        "source_type": req.source_type,
        "license": req.license,
    }


@activity.defn
async def index_chunks_activity(payload: dict[str, Any]) -> dict[str, Any]:
    """Index curated chunks to Qdrant (IndexWorkflow)."""
    from data_kernel.pipeline.chunking import chunk_text, title_from_url
    from data_kernel.pipeline.ingest_pipeline import IngestPipeline

    if payload.get("status") != "curated" or not payload.get("text"):
        return {
            "ok": True,
            "stage": "index",
            "skipped": True,
            "reason": "not_curated_or_no_text",
        }

    indexer = _build_indexer()
    store, writer = _store_and_writer()
    pipeline = IngestPipeline(
        store=store,
        writer=writer,
        indexer=indexer,
        index_on_curate=indexer is not None,
        index_required=os.getenv("INDEX_REQUIRED", "false").lower()
        in ("1", "true", "yes"),
    )
    text = payload["text"]
    document_id = str(payload.get("document_id") or payload.get("job_id") or "doc")
    chunks = chunk_text(
        text,
        source_id=document_id,
        document_id=document_id,
        job_id=payload.get("job_id"),
        source_url=payload.get("source_url"),
        title=title_from_url(payload.get("source_url") or ""),
        lang=payload.get("language") or "en",
        license=payload.get("license") or "unknown",
        checksum=payload.get("content_hash") or "",
        manifest_id=payload.get("manifest_id"),
    )
    for ch in chunks:
        ch["doc_id"] = f"{document_id}:chunk:{ch.get('chunk_index', 0)}"
    stages: dict[str, Any] = {}
    err = pipeline._maybe_index(chunks=chunks, document_id=document_id, stages=stages)  # noqa: SLF001
    # also ensure lake chunks exist
    writer.write_chunks(chunks, document_id=document_id, job_id=str(payload.get("job_id") or ""))
    return {
        "ok": err is None,
        "stage": "index",
        "error": err,
        **stages.get("index", {}),
    }


@activity.defn
async def graph_build_activity(payload: dict[str, Any]) -> dict[str, Any]:
    """Optional lightweight graph seed touch (not full NLP entity extraction)."""
    try:
        from memory.graph.neo4j_store import InMemoryGraphStore

        # Dev: ensure default seed exists; production would extract entities from text
        g = InMemoryGraphStore()
        seeded = g.seed_default()
        return {"ok": True, "stage": "graph_build", "seeded": seeded, "mode": "seed_ensure"}
    except Exception as exc:
        return {"ok": False, "stage": "graph_build", "error": str(exc)}


@activity.defn
async def validate_and_ingest_activity(payload: dict[str, Any]) -> dict[str, Any]:
    """Backward-compatible single-shot full pipeline activity."""
    from data_kernel.pipeline.ingest_pipeline import IngestPipeline, IngestRequest

    store, writer = _store_and_writer()
    indexer = _build_indexer()
    pipeline = IngestPipeline(
        store=store,
        writer=writer,
        indexer=indexer,
        index_on_curate=indexer is not None,
        index_required=os.getenv("INDEX_REQUIRED", "false").lower()
        in ("1", "true", "yes"),
    )
    req = IngestRequest(
        source_url=payload["source_url"],
        source_type=payload.get("source_type", "web"),
        license=payload.get("license", "unknown"),
        content=payload.get("content"),
        job_id=payload.get("job_id"),
        allow_list=payload.get("allow_list"),
    )
    result = pipeline.run(req)
    return {
        "job_id": result.job_id,
        "status": result.status,
        "stages": result.stages,
        "raw_uri": result.raw_uri,
        "curated_uri": result.curated_uri,
        "quarantine_uri": result.quarantine_uri,
        "manifest_id": result.manifest_id,
        "content_hash": result.content_hash,
        "error": result.error,
        "language": result.language,
        "chunk_count": result.chunk_count,
    }


# --- Workflows ---


@workflow.defn
class IngestWorkflow:
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await workflow.execute_activity(
            ingest_source_activity,
            payload,
            start_to_close_timeout=timedelta(minutes=10),
        )


@workflow.defn
class CurationWorkflow:
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await workflow.execute_activity(
            curation_filter_activity,
            payload,
            start_to_close_timeout=timedelta(minutes=10),
        )


@workflow.defn
class CurationFilterWorkflow:
    """Alias for plan name curation_filter_workflow."""

    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await workflow.execute_activity(
            curation_filter_activity,
            payload,
            start_to_close_timeout=timedelta(minutes=10),
        )


@workflow.defn
class IndexWorkflow:
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        idx = await workflow.execute_activity(
            index_chunks_activity,
            payload,
            start_to_close_timeout=timedelta(minutes=10),
        )
        graph = await workflow.execute_activity(
            graph_build_activity,
            payload,
            start_to_close_timeout=timedelta(minutes=5),
        )
        return {"index": idx, "graph": graph}


@workflow.defn
class GraphBuildWorkflow:
    """Plan name graph_build_workflow — optional Neo4j seed / entity touch."""

    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await workflow.execute_activity(
            graph_build_activity,
            payload,
            start_to_close_timeout=timedelta(minutes=5),
        )


@workflow.defn
class IngestionWorkflow:
    """
    End-to-end: Ingest → Curation → Index (plan Phase 2).
    Also remains callable as single workflow from the API.
    """

    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        # Prefer multi-stage; fall back to monolith activity on failure of split
        try:
            ingested = await workflow.execute_activity(
                ingest_source_activity,
                payload,
                start_to_close_timeout=timedelta(minutes=10),
            )
            if not ingested.get("ok"):
                return {"status": "failed", "stage": "ingest", **ingested}

            curate_payload = {
                **payload,
                **ingested,
                "source_url": payload.get("source_url"),
                "license": payload.get("license", "unknown"),
            }
            curated = await workflow.execute_activity(
                curation_filter_activity,
                curate_payload,
                start_to_close_timeout=timedelta(minutes=10),
            )
            if not curated.get("ok") and curated.get("status") not in (
                "curated",
                "image_stored",
            ):
                return curated

            index_payload = {**payload, **curated}
            indexed = await workflow.execute_activity(
                index_chunks_activity,
                index_payload,
                start_to_close_timeout=timedelta(minutes=10),
            )
            graph = await workflow.execute_activity(
                graph_build_activity,
                index_payload,
                start_to_close_timeout=timedelta(minutes=5),
            )
            return {
                "status": curated.get("status", "curated"),
                "job_id": curated.get("job_id") or payload.get("job_id"),
                "ingest": ingested,
                "curation": curated,
                "index": indexed,
                "graph": graph,
                "raw_uri": curated.get("raw_uri") or ingested.get("raw_uri"),
                "curated_uri": curated.get("curated_uri"),
                "quarantine_uri": curated.get("quarantine_uri"),
                "manifest_id": curated.get("manifest_id"),
                "content_hash": curated.get("content_hash"),
                "stages": curated.get("stages"),
                "error": curated.get("error"),
            }
        except Exception:
            # Monolith fallback for compatibility
            return await workflow.execute_activity(
                validate_and_ingest_activity,
                payload,
                start_to_close_timeout=timedelta(minutes=15),
            )


# Type-specific entry workflows (child IngestionWorkflow; source_type drives connector)
@workflow.defn
class IngestWebWorkflow:
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        p = {**payload, "source_type": payload.get("source_type") or "web"}
        return await workflow.execute_child_workflow(
            IngestionWorkflow.run,
            p,
            id=f"ingest-web-{p.get('job_id') or workflow.info().workflow_id}",
        )


@workflow.defn
class IngestPdfWorkflow:
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        p = {**payload, "source_type": "pdf"}
        return await workflow.execute_child_workflow(
            IngestionWorkflow.run,
            p,
            id=f"ingest-pdf-{p.get('job_id') or workflow.info().workflow_id}",
        )


async def main() -> None:
    address = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
    client = await Client.connect(address)
    worker = Worker(
        client,
        task_queue="agrimind-ingestion",
        workflows=[
            IngestionWorkflow,
            IngestWorkflow,
            CurationWorkflow,
            CurationFilterWorkflow,
            IndexWorkflow,
            GraphBuildWorkflow,
            IngestWebWorkflow,
            IngestPdfWorkflow,
        ],
        activities=[
            ingest_source_activity,
            curation_filter_activity,
            index_chunks_activity,
            graph_build_activity,
            validate_and_ingest_activity,
        ],
    )
    logger.info(
        "curation-worker running",
        queue="agrimind-ingestion",
        temporal=address,
        workflows=[
            "IngestionWorkflow",
            "IngestWorkflow",
            "CurationWorkflow",
            "CurationFilterWorkflow",
            "IndexWorkflow",
            "GraphBuildWorkflow",
            "IngestWebWorkflow",
            "IngestPdfWorkflow",
        ],
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
