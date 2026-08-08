"""Data ingestion API — Temporal/local pipeline + QA console APIs (Phase 2)."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import structlog
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from data_ingestion_service.qa import (
    PIPELINE_STAGE_ORDER,
    build_dashboard,
    build_report,
    build_run_failure_report,
    corpus_detail,
    enrich_job,
    quality_detail,
    quarantine_detail,
    stage_progress,
)

logger = structlog.get_logger()

# In-memory job registry (replace with Postgres in production)
_JOBS: dict[str, dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()

# Parallel local workers for live multi-source ingest
_EXECUTOR = ThreadPoolExecutor(
    max_workers=int(os.getenv("INGEST_WORKERS", "4")),
    thread_name_prefix="ingest",
)

# Shared indexer for local mode (optional; built lazily)
_INDEXER: Any | None = None
_INDEXER_TRIED = False


class IngestReq(BaseModel):
    source_url: str = Field(..., min_length=1)
    source_type: Literal[
        "web", "pdf", "wikipedia", "rss", "json", "image", "audio", "structured"
    ] = "web"
    license: str = "unknown"
    content: str | None = Field(
        default=None,
        description="Optional inline content — DEMO only (forbidden in real mode)",
    )
    local_path: str | None = Field(
        default=None,
        description="Optional local file path (PDF/text) under data/ (real: source_cache only)",
    )
    mode: Literal["auto", "temporal", "local"] = "auto"
    acq_mode: Literal["demo", "real"] = Field(
        default="real",
        description="demo = mock/example allowed; real = trusted live sources only",
    )
    run_id: str | None = Field(
        default=None,
        description="Existing acquisition run id; auto-created when omitted",
    )
    async_run: bool = Field(
        default=False,
        description="If true, queue local pipeline in a worker thread and return immediately "
        "so the dashboard can show live stage progress.",
    )
    title: str | None = None
    provider: str | None = None
    workflow: Literal[
        "IngestionWorkflow",
        "IngestWebWorkflow",
        "IngestPdfWorkflow",
        "IngestWorkflow",
        "CurationWorkflow",
        "CurationFilterWorkflow",
        "IndexWorkflow",
        "GraphBuildWorkflow",
    ] = "IngestionWorkflow"


class BatchIngestReq(BaseModel):
    """Start multiple sources in parallel (task-wise live progress)."""

    sources: list[IngestReq] | None = Field(
        default=None,
        description="Explicit sources; if omitted and acq_mode=real, uses real_source_catalog()",
    )
    use_catalog: bool = Field(
        default=True,
        description="When sources empty and acq_mode=real, pull real agri catalog",
    )
    include_heavy: bool = Field(
        default=True,
        description="Include PDF book downloads from catalog (FAO / Archive)",
    )
    max_workers: int = Field(default=4, ge=1, le=16)
    mode: Literal["local", "auto"] = "local"
    acq_mode: Literal["demo", "real"] = Field(
        default="real",
        description="real = no example/demo URLs; demo = QA mocks only",
    )
    run_id: str | None = None
    label: str | None = None
    limit: int | None = Field(
        default=None,
        ge=1,
        le=50,
        description="Optional cap on catalog size",
    )


class JobStatus(BaseModel):
    job_id: str
    status: str
    source_url: str
    result: dict[str, Any] | None = None
    created_at: str
    updated_at: str


def _settings():
    try:
        from agrimind_kernel.config.settings import get_settings

        return get_settings()
    except Exception:
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("data-ingestion-service starting")
    yield


app = FastAPI(
    title="data-ingestion-service",
    version="0.2.0",
    description="Phase 2 Data Acquisition Plane API + QA transparency console backend",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    from data_ingestion_service.runs import list_runs, runs_root

    return {
        "status": "healthy",
        "service": "data-ingestion-service",
        "version": "0.3.0",
        "jobs": len(_JOBS),
        "pipeline_stages": len(PIPELINE_STAGE_ORDER),
        "runs_root": str(runs_root()),
        "runs_count": len(list_runs(limit=500)),
        "modes": ["demo", "real"],
    }


# ─── Runs / process detail / cleanup ─────────────────────────────────────────


class CreateRunReq(BaseModel):
    acq_mode: Literal["demo", "real"] = "real"
    label: str | None = None
    run_id: str | None = None


class CleanupReq(BaseModel):
    """Reset / free disk: delete run folders and optional legacy lakehouse."""

    dry_run: bool = True
    mode: Literal["demo", "real"] | None = None
    run_id: str | None = Field(default=None, description="Delete a single run")
    older_than_hours: float | None = Field(
        default=None, description="Only runs older than this many hours"
    )
    keep_latest: int = Field(default=0, ge=0, le=100)
    include_legacy_lakehouse: bool = Field(
        default=False,
        description="Also wipe shared data/lakehouse (pre-runId layout)",
    )
    confirm: bool = Field(
        default=False,
        description="Must be true when dry_run=false to actually delete",
    )


@app.post("/v1/runs")
async def create_run_ep(req: CreateRunReq | None = None):
    """Start a new acquisition run folder (demo or real)."""
    body = req or CreateRunReq()
    from data_ingestion_service.runs import create_run

    ctx = create_run(body.acq_mode, label=body.label, run_id=body.run_id)
    return ctx.to_dict()


@app.get("/v1/runs")
async def list_runs_ep(
    acq_mode: Literal["demo", "real"] | None = None,
    limit: int = Query(default=50, ge=1, le=200),
):
    from data_ingestion_service.runs import list_runs

    rows = list_runs(mode=acq_mode, limit=limit)
    return {"count": len(rows), "runs": rows}


@app.get("/v1/runs/{run_id}")
async def get_run_detail(run_id: str, log_limit: int = Query(default=200, ge=1, le=2000)):
    """Process detail view: meta, paths, jobs, process log events, partial summary."""
    from data_ingestion_service.runs import get_run, read_process_log

    ctx = get_run(run_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="run not found")
    jobs = [enrich_job(j) for j in _JOBS.values() if j.get("run_id") == run_id]
    # also load disk snapshots if memory empty (after restart)
    if not jobs and ctx.jobs_dir.exists():
        for p in sorted(ctx.jobs_dir.glob("*.json")):
            try:
                jobs.append(enrich_job(json.loads(p.read_text(encoding="utf-8"))))
            except Exception:
                continue
    # recompute progress honesty
    jobs = [enrich_job(j) for j in jobs]
    by_status: dict[str, int] = {}
    for j in jobs:
        s = str(j.get("status") or "unknown")
        by_status[s] = by_status.get(s, 0) + 1
    ok_n = by_status.get("curated", 0) + by_status.get("image_stored", 0)
    bad_n = by_status.get("failed", 0) + by_status.get("quarantine", 0)
    outcome = (
        "success"
        if ok_n and not bad_n
        else "partial"
        if ok_n and bad_n
        else "failed"
        if bad_n
        else "running"
        if by_status.get("processing") or by_status.get("queued")
        else "empty"
    )
    return {
        "run": ctx.to_dict(),
        "outcome": outcome,
        "partial": outcome == "partial",
        "jobs_by_status": by_status,
        "jobs": jobs,
        "process_log": read_process_log(run_id, limit=log_limit),
        "folder_tree": _run_folder_tree(ctx.root),
    }


@app.get("/v1/runs/{run_id}/report")
async def get_run_failure_report(run_id: str):
    """Failed + partial success tracking report for a run (includes partial corpus)."""
    from data_ingestion_service.runs import get_run

    ctx = get_run(run_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="run not found")
    jobs = [j for j in _JOBS.values() if j.get("run_id") == run_id]
    if not jobs and ctx.jobs_dir.exists():
        for p in sorted(ctx.jobs_dir.glob("*.json")):
            try:
                jobs.append(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                continue
    report = build_run_failure_report(
        jobs,
        run_id=run_id,
        acq_mode=ctx.mode,
        local_root=str(ctx.lakehouse_objects),
        table_root=str(ctx.lakehouse_tables),
    )
    # Persist for tracking under the run folder
    try:
        out = ctx.root / "reports"
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"{report['report_id']}.json"
        path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        report["saved_path"] = str(path)
        ctx.append_event("failure_report", {"report_id": report["report_id"], "outcome": report["outcome"]})
    except Exception as exc:
        report["save_error"] = str(exc)
    return report


@app.get("/v1/runs/{run_id}/corpus")
async def get_run_corpus(run_id: str, limit: int = Query(default=100, ge=1, le=2000)):
    """Partial corpus for a run (curated docs/chunks even if other jobs failed)."""
    from data_ingestion_service.runs import get_run

    ctx = get_run(run_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="run not found")
    corp = corpus_detail(
        limit=limit,
        local_root=str(ctx.lakehouse_objects),
        table_root=str(ctx.lakehouse_tables),
    )
    corp["run_id"] = run_id
    corp["acq_mode"] = ctx.mode
    return corp


@app.delete("/v1/runs/{run_id}")
async def delete_run_ep(run_id: str, dry_run: bool = Query(default=False)):
    from data_ingestion_service.runs import cleanup_run

    # drop in-memory jobs for this run
    if not dry_run:
        with _JOBS_LOCK:
            gone = [jid for jid, j in _JOBS.items() if j.get("run_id") == run_id]
            for jid in gone:
                _JOBS.pop(jid, None)
    return cleanup_run(run_id, dry_run=dry_run)


@app.post("/v1/admin/cleanup")
async def admin_cleanup(req: CleanupReq | None = None):
    """
    Cleanup generated data to free space.
    Default dry_run=true (preview only). Set dry_run=false AND confirm=true to delete.
    """
    body = req or CleanupReq()
    from data_ingestion_service.runs import cleanup_run, cleanup_runs

    if not body.dry_run and not body.confirm:
        raise HTTPException(
            status_code=400,
            detail="set confirm=true with dry_run=false to actually delete data",
        )
    if body.run_id:
        if not body.dry_run:
            with _JOBS_LOCK:
                for jid in [j for j, v in _JOBS.items() if v.get("run_id") == body.run_id]:
                    _JOBS.pop(jid, None)
        return {"scope": "single_run", **cleanup_run(body.run_id, dry_run=body.dry_run)}

    if not body.dry_run:
        # clear matching in-memory jobs
        with _JOBS_LOCK:
            keep = {
                jid: j
                for jid, j in _JOBS.items()
                if body.mode and j.get("acq_mode") != body.mode
            }
            if body.mode:
                # remove jobs of that mode
                for jid in list(_JOBS.keys()):
                    if _JOBS[jid].get("acq_mode") == body.mode:
                        _JOBS.pop(jid, None)
            elif body.include_legacy_lakehouse and body.older_than_hours is None and body.keep_latest == 0:
                _JOBS.clear()

    result = cleanup_runs(
        mode=body.mode,
        older_than_hours=body.older_than_hours,
        keep_latest=body.keep_latest,
        dry_run=body.dry_run,
        include_legacy_lakehouse=body.include_legacy_lakehouse,
    )
    return {"scope": "bulk", **result}


def _run_folder_tree(root: Path, max_depth: int = 3) -> list[dict[str, Any]]:
    """Shallow folder listing for process view UI."""
    out: list[dict[str, Any]] = []
    if not root.exists():
        return out

    def walk(p: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        except Exception:
            return
        for e in entries[:80]:
            try:
                size = e.stat().st_size if e.is_file() else None
            except Exception:
                size = None
            rel = str(e.relative_to(root)).replace("\\", "/")
            out.append(
                {
                    "path": rel,
                    "type": "dir" if e.is_dir() else "file",
                    "size_bytes": size,
                }
            )
            if e.is_dir() and depth < max_depth:
                walk(e, depth + 1)

    walk(root, 0)
    return out


@app.get("/ready")
async def ready():
    return {"status": "ready"}


@app.post("/v1/ingest")
async def ingest(req: IngestReq):
    """
    Accept a source for ingestion.
    - acq_mode=demo: example/inline mock OK (isolated under data/runs/demo-*)
    - acq_mode=real: trusted live URLs only — no example.com / no inline mock content
    - async_run=true: queue local work and return immediately (live stage progress)
    """
    run_ctx = _ensure_run(req)
    acq_mode = run_ctx.mode
    job_id, now = _register_job(req, run_id=run_ctx.run_id, acq_mode=acq_mode)
    payload = _payload_from_req(req, job_id, run_id=run_ctx.run_id, acq_mode=acq_mode)

    mode = req.mode
    used = mode
    result: dict[str, Any] | None = None
    workflow_id: str | None = None

    if mode in ("temporal", "auto") and not req.async_run and acq_mode == "real":
        try:
            result = await _start_temporal(payload, workflow_name=req.workflow)
            used = "temporal"
            workflow_id = result.get("workflow_id")
            if result.get("status") == "workflow_started":
                _update_job(
                    job_id,
                    {
                        "status": "processing",
                        "result": result,
                        "workflow": req.workflow,
                    },
                )
                return {
                    "job_id": job_id,
                    "run_id": run_ctx.run_id,
                    "acq_mode": acq_mode,
                    "status": "processing",
                    "mode": used,
                    "workflow": req.workflow,
                    "workflow_id": workflow_id,
                    "source_url": req.source_url,
                    "paths": run_ctx.to_dict()["paths"],
                    "queued_at": now,
                    "note": f"Temporal {req.workflow} started; poll GET /v1/jobs/{{job_id}} or /v1/runs/{{run_id}}",
                }
        except Exception as exc:
            logger.warning("temporal_start_failed", error=str(exc), mode=mode)
            if mode == "temporal":
                _update_job(job_id, {"status": "failed", "result": {"error": str(exc)}})
                raise HTTPException(status_code=503, detail=f"Temporal unavailable: {exc}") from exc
            used = "local_fallback"

    # local pipeline path — optional async for live dashboard updates
    if req.async_run or used in ("local", "local_fallback", "auto"):
        if req.async_run or mode in ("local", "auto"):
            if req.async_run:
                _update_job(
                    job_id,
                    {
                        "status": "processing",
                        "progress": stage_progress({}, "processing"),
                        "result": {"status": "processing", "stages": {}},
                    },
                )
                _EXECUTOR.submit(_run_local_and_update, payload)
                return {
                    "job_id": job_id,
                    "run_id": run_ctx.run_id,
                    "acq_mode": acq_mode,
                    "status": "processing",
                    "mode": "local_async",
                    "source_url": req.source_url,
                    "source_type": req.source_type,
                    "paths": run_ctx.to_dict()["paths"],
                    "queued_at": now,
                    "note": "Local pipeline running; poll GET /v1/runs/{run_id} for process detail",
                }

    result = _run_local(payload)
    progress = stage_progress(result.get("stages") or {}, result.get("status"))
    _update_job(
        job_id,
        {
            "status": result.get("status", "failed"),
            "result": result,
            "progress": progress,
        },
    )
    return {
        "job_id": job_id,
        "run_id": run_ctx.run_id,
        "acq_mode": acq_mode,
        "status": result.get("status"),
        "mode": used if used != "auto" else "local",
        "source_url": req.source_url,
        "source_type": req.source_type,
        "raw_uri": result.get("raw_uri"),
        "curated_uri": result.get("curated_uri"),
        "quarantine_uri": result.get("quarantine_uri"),
        "manifest_id": result.get("manifest_id"),
        "content_hash": result.get("content_hash"),
        "stages": result.get("stages"),
        "progress": progress,
        "language": result.get("language"),
        "chunk_count": result.get("chunk_count"),
        "error": result.get("error"),
        "paths": run_ctx.to_dict()["paths"],
        "queued_at": now,
    }


@app.get("/v1/sources/catalog")
async def sources_catalog(include_heavy: bool = Query(default=True)):
    """List curated real agri sources (Wikipedia, FAO, USDA, ICAR, Archive)."""
    from data_kernel.sources.discovery import DEFAULT_ALLOW_LIST, real_source_catalog

    rows = real_source_catalog(include_heavy=include_heavy)
    return {
        "count": len(rows),
        "allow_list": list(DEFAULT_ALLOW_LIST),
        "sources": rows,
        "note": (
            "Open/government/Wikipedia sources for production-like DAQ runs. "
            "POST /v1/ingest/batch to start them in parallel with live progress."
        ),
    }


@app.get("/v1/sources/discovery-services")
async def sources_discovery_services():
    """List keyword-based online discovery providers (Wikipedia, OL, Archive, FAO…)."""
    from data_kernel.sources.agri_taxonomy import list_categories
    from data_kernel.sources.discovery import DEFAULT_ALLOW_LIST
    from data_kernel.sources.keyword_discovery_service import AGRI_KEYWORD_MAP
    from data_kernel.sources.online_discovery import list_discovery_services

    return {
        "services": list_discovery_services(),
        "categories": list_categories(),
        "languages": ["en", "hi", "mr"],
        "keyword_topics": list(AGRI_KEYWORD_MAP.keys()),
        "allow_list": list(DEFAULT_ALLOW_LIST),
        "allow_list_size": len(DEFAULT_ALLOW_LIST),
        "note": (
            "Agri/farmer domain only (EN/HI/MR). "
            "POST /v1/sources/discover-keywords or /v1/sources/discover-online."
        ),
    }


@app.get("/v1/sources/keywords")
async def sources_keywords(
    categories: str | None = Query(
        default=None,
        description="Comma-separated category ids (see /v1/sources/discovery-services)",
    ),
    limit_per_category: int = Query(default=6, ge=1, le=20),
):
    """Agri taxonomy keywords for selected categories (or all)."""
    from data_kernel.sources.agri_taxonomy import keywords_for_categories, list_categories

    cats = [c.strip() for c in (categories or "").split(",") if c.strip()] or None
    kws = keywords_for_categories(cats, limit_per_category=limit_per_category)
    return {
        "categories": cats or [c["id"] for c in list_categories()],
        "keywords": kws,
        "count": len(kws),
        "taxonomy": list_categories(),
    }


class DiscoverOnlineReq(BaseModel):
    """Keyword discovery over trusted open agri sources."""

    query: str | None = Field(default=None, description="Free-text agri query")
    categories: list[str] | None = Field(
        default=None,
        description="Taxonomy category ids, e.g. soil_health, pests_ipm, crops",
    )
    keywords: list[str] | None = None
    services: list[str] | None = Field(
        default=None,
        description="Subset of discovery service ids",
    )
    lang: str = "en"
    per_keyword_limit: int = Field(default=3, ge=1, le=10)
    max_keywords: int = Field(default=6, ge=1, le=20)
    max_results: int = Field(default=40, ge=1, le=100)
    check_access: bool = Field(
        default=True,
        description="HTTP HEAD/GET probe for top allowed URLs",
    )
    pdf_only: bool = False
    books_bias: bool = Field(
        default=False,
        description="Prefer Open Library / Internet Archive book PDFs",
    )
    max_access_checks: int = Field(default=15, ge=0, le=40)
    workers: int = Field(default=6, ge=1, le=12)
    auto_ingest: bool = Field(
        default=False,
        description="If true, start parallel ingest for ingest_ready sources",
    )
    auto_ingest_limit: int = Field(default=8, ge=1, le=30)


@app.post("/v1/sources/discover-online")
async def sources_discover_online(req: DiscoverOnlineReq | None = None):
    """
    Auto-discover trusted open agri/farmer sources by keywords.

    Searches Wikipedia, Open Library, Internet Archive, Commons PDFs, plus
    FAO/USDA/ICAR portal seeds. Filters allow-list and optionally probes access.
    """
    body = req or DiscoverOnlineReq()
    from data_kernel.sources.online_discovery import discover_online

    result = discover_online(
        query=body.query,
        categories=body.categories,
        keywords=body.keywords,
        services=body.services,
        lang=body.lang,
        per_keyword_limit=body.per_keyword_limit,
        max_keywords=body.max_keywords,
        max_results=body.max_results,
        check_access_flag=body.check_access,
        pdf_only=body.pdf_only,
        books_bias=body.books_bias,
        max_access_checks=body.max_access_checks,
        workers=body.workers,
    )

    ingest_jobs: list[dict[str, Any]] = []
    if body.auto_ingest and result.get("ingest_ready"):
        ready = result["ingest_ready"][: body.auto_ingest_limit]
        batch_items = [
            IngestReq(
                source_url=str(s["source_url"]),
                source_type=s.get("source_type") or "web",  # type: ignore[arg-type]
                license=str(s.get("license") or "unknown"),
                mode="local",
                acq_mode="real",
                content=None,
                async_run=True,
                title=s.get("title"),  # type: ignore[arg-type]
                provider=s.get("provider"),  # type: ignore[arg-type]
            )
            for s in ready
        ]
        batch_res = await ingest_batch(
            BatchIngestReq(
                sources=batch_items,
                use_catalog=False,
                mode="local",
                acq_mode="real",
                label="discover-online-real",
            )
        )
        ingest_jobs = list(batch_res.get("jobs") or [])
        result["auto_ingest"] = {
            "started": len(ingest_jobs),
            "jobs": ingest_jobs,
            "run_id": batch_res.get("run_id"),
            "acq_mode": "real",
        }
    return result


@app.get("/v1/sources/discover-online")
async def sources_discover_online_get(
    q: str | None = Query(default=None, description="Free-text agri query"),
    categories: str | None = Query(default=None, description="Comma-separated category ids"),
    pdf_only: bool = Query(default=False),
    books: bool = Query(default=False, description="Bias toward PDF books"),
    check_access: bool = Query(default=True),
    max_results: int = Query(default=25, ge=1, le=100),
    max_keywords: int = Query(default=5, ge=1, le=15),
):
    """GET convenience wrapper for online keyword discovery."""
    cats = [c.strip() for c in (categories or "").split(",") if c.strip()] or None
    body = DiscoverOnlineReq(
        query=q,
        categories=cats,
        pdf_only=pdf_only,
        books_bias=books,
        check_access=check_access,
        max_results=max_results,
        max_keywords=max_keywords,
    )
    return await sources_discover_online(body)


class DiscoverKeywordsReq(BaseModel):
    """Multilingual keyword discovery (EN / HI / MR) — plan AutoSourceDiscoveryService."""

    keywords: list[str] = Field(..., min_length=1)
    languages: list[str] = Field(default_factory=lambda: ["en", "hi", "mr"])
    source_types: list[str] = Field(
        default_factory=lambda: ["wikipedia", "pdf", "web"]
    )
    max_results: int = Field(default=40, ge=1, le=100)
    check_access: bool = False
    auto_ingest: bool = False
    auto_ingest_limit: int = Field(default=8, ge=1, le=30)


@app.post("/v1/sources/discover-keywords")
async def sources_discover_keywords(req: DiscoverKeywordsReq):
    """
    Multilingual agri discovery: expand keywords EN/HI/MR, search Wikipedia
    (all langs) + Archive/OL/FAO (EN PDFs), allow-list + trust rank.
    """
    from data_kernel.sources.keyword_discovery_service import (
        AutoSourceDiscoveryService,
        expand_keywords,
    )

    langs = [x for x in req.languages if x in ("en", "hi", "mr")] or ["en", "hi", "mr"]
    svc = AutoSourceDiscoveryService(check_access=req.check_access)
    results = svc.discover_by_keywords(
        keywords=req.keywords,
        languages=langs,
        source_types=req.source_types,
        max_total=req.max_results,
    )
    payload: dict[str, Any] = {
        "keywords": req.keywords,
        "languages": langs,
        "expanded": expand_keywords(req.keywords, langs),
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
        ],
        "note": "EN/HI/MR agri discovery. Use auto_ingest or POST /v1/ingest/batch.",
    }
    if req.auto_ingest and payload["ingest_ready"]:
        ready = payload["ingest_ready"][: req.auto_ingest_limit]
        batch_items = [
            IngestReq(
                source_url=str(s["source_url"]),
                source_type=s.get("source_type") or "web",  # type: ignore[arg-type]
                license=str(s.get("license") or "unknown"),
                mode="local",
                acq_mode="real",
                content=None,
                async_run=True,
                title=s.get("title"),  # type: ignore[arg-type]
                provider=s.get("provider"),  # type: ignore[arg-type]
            )
            for s in ready
        ]
        batch_res = await ingest_batch(
            BatchIngestReq(
                sources=batch_items,
                use_catalog=False,
                mode="local",
                acq_mode="real",
                label="discover-keywords-real",
            )
        )
        payload["auto_ingest"] = {
            "started": len(batch_res.get("jobs") or []),
            "jobs": batch_res.get("jobs"),
            "run_id": batch_res.get("run_id"),
            "acq_mode": "real",
        }
    return payload


@app.post("/v1/sources/discover-pdf-books")
async def sources_discover_pdf_books(
    topic: str = Query(..., min_length=2),
    max_books: int = Query(default=10, ge=1, le=30),
    check_access: bool = Query(default=True),
):
    """Find open agri PDF books (Archive / Open Library / FAO)."""
    from data_kernel.sources.keyword_discovery_service import AutoSourceDiscoveryService

    svc = AutoSourceDiscoveryService(check_access=check_access)
    books = svc.find_pdf_books(topic, max_books=max_books)
    return {
        "topic": topic,
        "count": len(books),
        "sources": [b.to_dict() for b in books],
    }


class CheckAccessReq(BaseModel):
    url: str = Field(..., min_length=4)


@app.post("/v1/sources/check-access")
async def sources_check_access(req: CheckAccessReq):
    """Single-URL access report (allow-list, robots, HEAD/GET, trust)."""
    from data_kernel.sources.keyword_discovery_service import AutoSourceDiscoveryService

    return AutoSourceDiscoveryService().check_single_url(req.url)


@app.post("/v1/ingest/batch")
async def ingest_batch(req: BatchIngestReq | None = None):
    """
    Start multiple sources in parallel under one run_id.
    acq_mode=real (default): catalog / trusted URLs only — no example.com.
    acq_mode=demo: must pass explicit demo sources (catalog not used).
    """
    body = req or BatchIngestReq()
    acq_mode = body.acq_mode or "real"
    if acq_mode == "demo" and body.use_catalog and not body.sources:
        raise HTTPException(
            status_code=400,
            detail="demo_mode_cannot_use_real_catalog: set acq_mode=real or pass demo sources",
        )

    run_ctx = _ensure_run(acq_mode=acq_mode, run_id=body.run_id, label=body.label)
    items: list[IngestReq] = list(body.sources or [])
    if not items and body.use_catalog and acq_mode == "real":
        from data_kernel.sources.discovery import real_source_catalog

        catalog = real_source_catalog(include_heavy=body.include_heavy)
        if body.limit is not None:
            catalog = catalog[: body.limit]
        items = [
            IngestReq(
                source_url=str(c["source_url"]),
                source_type=c.get("source_type") or "web",  # type: ignore[arg-type]
                license=str(c.get("license") or "unknown"),
                mode=body.mode,
                acq_mode="real",
                run_id=run_ctx.run_id,
                async_run=True,
                title=c.get("title"),  # type: ignore[arg-type]
                provider=c.get("provider"),  # type: ignore[arg-type]
                content=None,
            )
            for c in catalog
        ]
    if not items:
        raise HTTPException(status_code=400, detail="no sources to ingest")

    # Real mode: attach trusted source_cache PDFs only
    if acq_mode == "real":
        from data_kernel.sources.discovery import real_source_catalog as _rsc

        cache_by_url = {
            str(c["source_url"]): c.get("local_cache")
            for c in _rsc(include_heavy=True)
            if c.get("local_cache")
        }
        cache_roots = [
            Path("."),
            Path("agrimind"),
            Path("data"),
        ]
        for it in items:
            it.acq_mode = "real"
            it.content = None  # hard strip
            if it.local_path:
                continue
            rel = cache_by_url.get(it.source_url)
            if not rel:
                continue
            for root in cache_roots:
                alts = [
                    (root / rel) if not Path(rel).is_absolute() else Path(rel),
                    root / "source_cache" / Path(rel).name,
                    root / "data" / "source_cache" / Path(rel).name,
                ]
                for p in alts:
                    if p.is_file():
                        it.local_path = str(p.resolve())
                        break
                if it.local_path:
                    break

    started: list[dict[str, Any]] = []
    for it in items:
        it.run_id = run_ctx.run_id
        it.acq_mode = acq_mode  # type: ignore[assignment]
        job_id, now = _register_job(it, run_id=run_ctx.run_id, acq_mode=acq_mode)
        payload = _payload_from_req(it, job_id, run_id=run_ctx.run_id, acq_mode=acq_mode)
        _update_job(
            job_id,
            {
                "status": "processing",
                "progress": stage_progress({}, "processing"),
                "result": {"status": "processing", "stages": {}},
                "batch": True,
            },
        )
        _EXECUTOR.submit(_run_local_and_update, payload)
        started.append(
            {
                "job_id": job_id,
                "run_id": run_ctx.run_id,
                "acq_mode": acq_mode,
                "status": "processing",
                "source_url": it.source_url,
                "source_type": it.source_type,
                "license": it.license,
                "title": it.title,
                "provider": it.provider,
                "queued_at": now,
            }
        )

    return {
        "batch": "real_sources_parallel" if acq_mode == "real" else "demo_sources_parallel",
        "run_id": run_ctx.run_id,
        "acq_mode": acq_mode,
        "count": len(started),
        "workers": body.max_workers,
        "mode": "local_async",
        "paths": run_ctx.to_dict()["paths"],
        "jobs": started,
        "note": "Poll GET /v1/runs/{run_id} for process folder + stage log.",
    }


@app.get("/v1/jobs/{job_id}")
async def get_job(job_id: str):
    job = _JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return enrich_job(job)


@app.get("/v1/jobs")
async def list_jobs(
    limit: int = 50,
    acq_mode: Literal["demo", "real"] | None = None,
    run_id: str | None = None,
):
    items = list(_JOBS.values())
    if acq_mode:
        items = [j for j in items if j.get("acq_mode") == acq_mode]
    if run_id:
        items = [j for j in items if j.get("run_id") == run_id]
    items = items[-limit:]
    enriched = [enrich_job(j) for j in items]
    return {
        "count": len(enriched),
        "jobs": enriched,
        "filter": {"acq_mode": acq_mode, "run_id": run_id},
    }


@app.get("/v1/lakehouse/manifests")
async def list_manifests(limit: int = 50):
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
    return {"manifests": writer.list_manifests(limit=limit)}


@app.post("/v1/discover")
async def discover(body: dict[str, Any]):
    """Stage 1: filter candidate sources by allow-list."""
    from data_kernel.sources.discovery import default_seed_catalog, discover_sources

    candidates = body.get("candidates") or default_seed_catalog()
    allow = body.get("allow_list")
    found = discover_sources(candidates, allow_list=allow)
    return {
        "count": len(found),
        "sources": [
            {
                "source_url": s.source_url,
                "source_type": s.source_type,
                "license": s.license,
                "allowed": s.allowed,
                "reason": s.reason,
            }
            for s in found
        ],
    }


@app.get("/v1/lakehouse/tables/{table}")
async def query_table(table: str, limit: int = 50):
    """Query JSONL lakehouse tables (Phase 2 catalog)."""
    from data_kernel.lakehouse.writer import LAKEHOUSE_TABLES

    allowed = set(LAKEHOUSE_TABLES)
    if table not in allowed:
        raise HTTPException(status_code=400, detail=f"table must be one of {sorted(allowed)}")
    from data_ingestion_service.qa import build_writer

    writer = build_writer()
    rows = writer.query_table(table, limit=limit)
    return {"table": table, "count": len(rows), "rows": rows}


@app.get("/v1/pipeline/stages")
async def pipeline_stages():
    """Stage catalog for progress UI (13+ pipeline stages)."""
    labels = {
        "allow_list": "1. Source discovery / allow-list",
        "license": "2. License validation",
        "robots": "2b. robots.txt",
        "download": "3. Download (size/retry/checksum)",
        "raw_write": "11. Raw immutable write",
        "normalize": "4. Unicode + language",
        "pii": "5. PII redaction",
        "toxicity": "6. Toxicity / safety",
        "relevance": "7. Agriculture relevance",
        "dedup": "8. Deduplication (exact + MinHash)",
        "quality": "9. Quality scoring",
        "provenance": "10. Provenance attachment",
        "curated_write": "12. Curated write",
        "chunks_write": "12b. Chunks table",
        "index": "Index (optional Qdrant)",
        "manifest": "Dataset manifest",
    }
    return {
        "stages": [
            {"key": k, "label": labels.get(k, k), "order": i + 1}
            for i, k in enumerate(PIPELINE_STAGE_ORDER)
        ]
    }


# ─── QA Console APIs (transparent evaluation) ───────────────────────────────


@app.get("/v1/qa/dashboard")
async def qa_dashboard(
    acq_mode: Literal["demo", "real"] | None = Query(default=None),
    run_id: str | None = Query(default=None),
):
    """Real-time KPIs. Filter by acq_mode and/or run_id for isolated views."""
    from data_ingestion_service.qa import build_dashboard_for_jobs
    from data_ingestion_service.runs import get_run

    jobs = list(_JOBS.values())
    if acq_mode:
        jobs = [j for j in jobs if j.get("acq_mode") == acq_mode]
    if run_id:
        jobs = [j for j in jobs if j.get("run_id") == run_id]
    local_root = table_root = None
    extra: dict[str, Any] = {"filter": {"acq_mode": acq_mode, "run_id": run_id}}
    if run_id:
        ctx = get_run(run_id)
        if ctx:
            local_root = str(ctx.lakehouse_objects)
            table_root = str(ctx.lakehouse_tables)
            extra["run"] = ctx.to_dict()
    return build_dashboard_for_jobs(
        jobs, local_root=local_root, table_root=table_root, extra=extra
    )


@app.get("/v1/qa/report")
async def qa_report(
    include_samples: bool = Query(default=True),
    sample_limit: int = Query(default=25, ge=1, le=200),
):
    """Full QA report with checklist score and sample rows for auditors."""
    return build_report(
        list(_JOBS.values()),
        include_samples=include_samples,
        sample_limit=sample_limit,
    )


@app.get("/v1/qa/corpus")
async def qa_corpus(
    limit: int = Query(default=100, ge=1, le=2000),
    run_id: str | None = Query(default=None),
    acq_mode: Literal["demo", "real"] | None = Query(default=None),
):
    """Ready corpus: prefer run-scoped lakehouse when run_id is set (shows partial data)."""
    from data_ingestion_service.runs import get_run, list_runs

    local_root = table_root = None
    if run_id:
        ctx = get_run(run_id)
        if not ctx:
            raise HTTPException(status_code=404, detail="run not found")
        local_root = str(ctx.lakehouse_objects)
        table_root = str(ctx.lakehouse_tables)
    elif acq_mode:
        # latest run of that mode with any data
        runs = list_runs(mode=acq_mode, limit=20)
        for r in runs:
            rid = r.get("run_id")
            if not rid:
                continue
            ctx = get_run(str(rid))
            if ctx and (ctx.lakehouse_tables / "curated.documents.jsonl").exists():
                local_root = str(ctx.lakehouse_objects)
                table_root = str(ctx.lakehouse_tables)
                run_id = ctx.run_id
                break
    corp = corpus_detail(limit=limit, local_root=local_root, table_root=table_root)
    corp["run_id"] = run_id
    corp["acq_mode"] = acq_mode
    return corp


@app.get("/v1/qa/quarantine")
async def qa_quarantine(limit: int = Query(default=100, ge=1, le=2000)):
    """Quarantine browser with reason breakdown + duplicate flags."""
    return quarantine_detail(limit=limit)


@app.get("/v1/qa/quality")
async def qa_quality(limit: int = Query(default=100, ge=1, le=2000)):
    """Quality tier breakdown for curated documents."""
    return quality_detail(limit=limit)


@app.get("/v1/qa/duplicates")
async def qa_duplicates(limit: int = Query(default=100, ge=1, le=2000)):
    """Duplicate / near-duplicate quarantine slice."""
    q = quarantine_detail(limit=limit)
    dups = [r for r in q["records"] if r.get("is_duplicate")]
    return {
        "count": len(dups),
        "duplicate_rate_note": "From quarantine.records reasons starting with duplicate:",
        "records": dups,
        "generated_at": q["generated_at"],
    }


class DemoBatchReq(BaseModel):
    """Seed a few inline samples so QA can evaluate the full pipeline offline."""

    include_quarantine_samples: bool = True
    mode: Literal["local", "auto"] = "local"
    label: str | None = "qa-demo-batch"


@app.post("/v1/qa/demo-batch")
async def qa_demo_batch(req: DemoBatchReq | None = None):
    """
    DEMO mode only: fixed inline samples (example.com).
    Isolated under data/runs/demo-* — never mixed into real runs.
    """
    body = req or DemoBatchReq()
    from data_ingestion_service.runs import create_run, finish_run

    run_ctx = create_run("demo", label=body.label or "qa-demo-batch")
    samples = [
        {
            "name": "good_agri",
            "source_url": "https://example.com/demo/cotton-ipm",
            "source_type": "web",
            "license": "cc-by",
            "content": (
                "ICAR advisory for farmers: cotton bollworm IPM practices, "
                "soil health monitoring, crop rotation, fertilizer and irrigation guidance "
                "for sustainable farming in Maharashtra and Gujarat."
            ),
        },
        {
            "name": "pii_redact",
            "source_url": "https://example.com/demo/farmer-contact",
            "source_type": "web",
            "license": "cc0",
            "content": (
                "Farmer soil crop pest IPM contact 9876543210 for fertilizer advice. "
                "Aadhaar 1234 5678 9012 is not required for scheme enrollment demo text."
            ),
        },
        {
            "name": "structured_soil",
            "source_url": "https://example.com/api/soil-demo",
            "source_type": "json",
            "license": "government_open",
            "content": (
                '{"crop":"cotton","soil":"black","n":120,"p":40,"k":40,'
                '"farm":"demo","advisory":"apply balanced NPK and monitor pest"}'
            ),
        },
    ]
    if body.include_quarantine_samples:
        samples.extend(
            [
                {
                    "name": "toxicity_block",
                    "source_url": "https://example.com/demo/unsafe",
                    "source_type": "web",
                    "license": "cc-by",
                    "content": "Crop farm soil. Please kill yourself now.",
                },
                {
                    "name": "low_relevance",
                    "source_url": "https://example.com/demo/crypto",
                    "source_type": "web",
                    "license": "cc-by",
                    "content": "Stock market crypto trading tips and NFT hype only.",
                },
            ]
        )

    results: list[dict[str, Any]] = []
    for s in samples:
        job_id = hashlib.sha256(
            f"demo:{run_ctx.run_id}:{s['name']}:{uuid.uuid4().hex}".encode()
        ).hexdigest()[:12]
        payload = {
            "job_id": job_id,
            "source_url": s["source_url"],
            "source_type": s["source_type"],
            "license": s["license"],
            "content": s["content"],
            "run_id": run_ctx.run_id,
            "acq_mode": "demo",
        }
        now = datetime.now(UTC).isoformat()
        with _JOBS_LOCK:
            _JOBS[job_id] = {
                "job_id": job_id,
                "status": "queued",
                "source_url": s["source_url"],
                "source_type": s["source_type"],
                "license": s["license"],
                "created_at": now,
                "updated_at": now,
                "result": None,
                "demo_name": s["name"],
                "acq_mode": "demo",
                "run_id": run_ctx.run_id,
            }
        run_ctx.touch_job(job_id)
        try:
            result = _run_local(payload)
            progress = stage_progress(result.get("stages") or {}, result.get("status"))
            _update_job(
                job_id,
                {
                    "status": result.get("status", "failed"),
                    "result": result,
                    "progress": progress,
                },
            )
            results.append(
                {
                    "name": s["name"],
                    "job_id": job_id,
                    "status": result.get("status"),
                    "error": result.get("error"),
                    "progress": progress,
                    "manifest_id": result.get("manifest_id"),
                }
            )
        except Exception as exc:
            _update_job(job_id, {"status": "failed", "result": {"error": str(exc)}})
            results.append(
                {"name": s["name"], "job_id": job_id, "status": "failed", "error": str(exc)}
            )

    # intentional near-duplicate of first good sample
    if results and results[0].get("status") == "curated":
        job_id = hashlib.sha256(
            f"demo:dup:{run_ctx.run_id}:{uuid.uuid4().hex}".encode()
        ).hexdigest()[:12]
        dup_payload = {
            "job_id": job_id,
            "source_url": "https://example.com/demo/cotton-ipm-copy",
            "source_type": "web",
            "license": "cc-by",
            "content": (
                "ICAR advisory for farmers: cotton bollworm IPM practices, "
                "soil health monitoring, crop rotation, fertilizer and irrigation guidance "
                "for sustainable farming in Maharashtra and Gujarat."
            ),
            "run_id": run_ctx.run_id,
            "acq_mode": "demo",
        }
        now = datetime.now(UTC).isoformat()
        with _JOBS_LOCK:
            _JOBS[job_id] = {
                "job_id": job_id,
                "status": "queued",
                "source_url": dup_payload["source_url"],
                "source_type": "web",
                "license": "cc-by",
                "created_at": now,
                "updated_at": now,
                "result": None,
                "demo_name": "near_duplicate",
                "acq_mode": "demo",
                "run_id": run_ctx.run_id,
            }
        run_ctx.touch_job(job_id)
        result = _run_local(dup_payload)
        progress = stage_progress(result.get("stages") or {}, result.get("status"))
        _update_job(
            job_id,
            {
                "status": result.get("status", "failed"),
                "result": result,
                "progress": progress,
            },
        )
        results.append(
            {
                "name": "near_duplicate",
                "job_id": job_id,
                "status": result.get("status"),
                "error": result.get("error"),
                "progress": progress,
            }
        )

    finish_run(run_ctx.run_id, status="completed")
    demo_jobs = [j for j in _JOBS.values() if j.get("run_id") == run_ctx.run_id]
    from data_ingestion_service.qa import build_dashboard_for_jobs

    return {
        "batch": "qa_demo",
        "acq_mode": "demo",
        "run_id": run_ctx.run_id,
        "paths": run_ctx.to_dict()["paths"],
        "count": len(results),
        "results": results,
        "dashboard": build_dashboard_for_jobs(
            demo_jobs,
            local_root=str(run_ctx.lakehouse_objects),
            table_root=str(run_ctx.lakehouse_tables),
            extra={"run_id": run_ctx.run_id, "acq_mode": "demo"},
        ),
    }


class ReindexReq(BaseModel):
    limit: int = Field(default=100, ge=1, le=5000)
    prefer_in_memory: bool = False


@app.post("/v1/index/curated")
async def reindex_curated(req: ReindexReq | None = None):
    """
    Reindex curated lakehouse rows into the vector store.
    Loads full text from object store when available; falls back to content_preview.
    """
    body = req or ReindexReq()
    from data_kernel.lakehouse.writer import LakehouseWriter
    from data_kernel.pipeline.chunking import chunk_text, title_from_url
    from data_kernel.storage.object_store import build_object_store

    store = build_object_store(
        prefer=os.getenv("OBJECT_STORE", "auto"),
        local_root=os.getenv("LAKEHOUSE_ROOT", "./data/lakehouse"),
        minio_endpoint=os.getenv("MINIO_ENDPOINT", "http://localhost:9000"),
        minio_access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
        minio_secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
    )
    writer = LakehouseWriter(store)
    rows = writer.query_table("curated.documents", limit=body.limit)
    indexer = _get_indexer(force_rebuild=body.prefer_in_memory, prefer_in_memory=body.prefer_in_memory)
    if indexer is None:
        raise HTTPException(status_code=503, detail="indexer unavailable (install memory package)")

    total_upserted = 0
    docs_seen = 0
    errors: list[str] = []
    for row in rows:
        docs_seen += 1
        text = _load_curated_text(store, row)
        if not text:
            errors.append(f"empty:{row.get('document_id')}")
            continue
        document_id = str(row.get("document_id") or row.get("job_id") or "")
        source_url = str(row.get("source_url") or "")
        chunks = chunk_text(
            text,
            source_id=document_id,
            document_id=document_id,
            job_id=row.get("job_id"),
            source_url=source_url,
            url_or_path=source_url,
            source_type=row.get("source_type") or "document",
            checksum=row.get("content_hash") or "",
            title=title_from_url(source_url),
            lang=row.get("language") or "en",
            license=row.get("license") or row.get("license_type"),
        )
        for ch in chunks:
            ch["doc_id"] = f"{document_id}:chunk:{ch.get('chunk_index', 0)}"
        try:
            total_upserted += int(indexer.index_chunks(chunks))
        except Exception as exc:
            errors.append(f"{document_id}:{exc}")

    return {
        "documents": docs_seen,
        "upserted": total_upserted,
        "backend": getattr(indexer, "backend", "unknown"),
        "errors": errors[:20],
    }


def _load_curated_text(store: Any, row: dict[str, Any]) -> str:
    bucket = row.get("bucket")
    key = row.get("object_key")
    if bucket and key:
        try:
            data = store.get_bytes(bucket, key)
            if data:
                return data.decode("utf-8", errors="replace")
        except Exception as exc:
            logger.warning("curated_object_read_failed", error=str(exc), key=key)
    return str(row.get("content_preview") or "")


def _index_on_ingest_enabled() -> bool:
    return os.getenv("INDEX_ON_INGEST", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _get_indexer(
    *,
    force_rebuild: bool = False,
    prefer_in_memory: bool = False,
) -> Any | None:
    """Build MemoryChunkIndexer when memory package is available."""
    global _INDEXER, _INDEXER_TRIED
    if not _index_on_ingest_enabled() and not force_rebuild:
        return None
    if _INDEXER is not None and not force_rebuild:
        return _INDEXER
    if _INDEXER_TRIED and not force_rebuild:
        return _INDEXER
    _INDEXER_TRIED = True
    try:
        from memory.indexing.curated_indexer import build_default_indexer

        _INDEXER = build_default_indexer(
            qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333"),
            collection=os.getenv("QDRANT_COLLECTION", "agrimind_chunks"),
            prefer_in_memory=prefer_in_memory
            or os.getenv("INDEX_PREFER_IN_MEMORY", "").lower() in ("1", "true", "yes"),
        )
        logger.info(
            "curated_indexer_ready",
            backend=getattr(_INDEXER, "backend", "unknown"),
        )
        return _INDEXER
    except Exception as exc:
        logger.warning("curated_indexer_unavailable", error=str(exc))
        _INDEXER = None
        return None


def _ensure_run(req: IngestReq | None = None, *, acq_mode: str | None = None, run_id: str | None = None, label: str | None = None):
    from data_ingestion_service.runs import create_run, get_run

    mode = (acq_mode or (req.acq_mode if req else None) or "real")  # type: ignore[union-attr]
    if mode not in ("demo", "real"):
        mode = "real"
    rid = run_id or (req.run_id if req else None)
    if rid:
        ctx = get_run(rid)
        if ctx:
            if ctx.mode != mode:
                raise HTTPException(
                    status_code=400,
                    detail=f"run {rid} is mode={ctx.mode}, request mode={mode}",
                )
            return ctx
    return create_run(mode, label=label, run_id=rid)  # type: ignore[arg-type]


def _register_job(req: IngestReq, *, run_id: str, acq_mode: str) -> tuple[str, str]:
    from data_ingestion_service.runs import get_run, validate_source_for_mode

    try:
        validate_source_for_mode(
            mode=acq_mode,  # type: ignore[arg-type]
            source_url=req.source_url,
            content=req.content,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job_id = hashlib.sha256(
        f"{acq_mode}:{run_id}:{req.source_url}:{uuid.uuid4().hex}".encode()
    ).hexdigest()[:12]
    now = datetime.now(UTC).isoformat()
    with _JOBS_LOCK:
        _JOBS[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "source_url": req.source_url,
            "source_type": req.source_type,
            "license": req.license,
            "title": req.title,
            "provider": req.provider,
            "acq_mode": acq_mode,
            "run_id": run_id,
            "created_at": now,
            "updated_at": now,
            "result": None,
            "progress": stage_progress({}, "queued"),
        }
    ctx = get_run(run_id)
    if ctx:
        ctx.touch_job(job_id)
        ctx.append_event("job_queued", {"job_id": job_id, "source_url": req.source_url})
    return job_id, now


def _payload_from_req(req: IngestReq, job_id: str, *, run_id: str, acq_mode: str) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "source_url": req.source_url,
        "source_type": req.source_type,
        "license": req.license,
        "content": req.content if acq_mode == "demo" else None,
        "local_path": req.local_path,
        "title": req.title,
        "provider": req.provider,
        "run_id": run_id,
        "acq_mode": acq_mode,
    }


def _update_job(job_id: str, fields: dict[str, Any]) -> None:
    from data_ingestion_service.runs import update_run_stats_from_job

    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return
        job.update(fields)
        job["updated_at"] = datetime.now(UTC).isoformat()
        snap = dict(job)
        run_id = job.get("run_id")
    if run_id and fields.get("status") in (
        "curated",
        "quarantine",
        "failed",
        "image_stored",
        "processing",
    ):
        try:
            update_run_stats_from_job(str(run_id), snap)
        except Exception:
            pass


def _load_local_bytes(path: str | None, *, acq_mode: str = "real") -> bytes | None:
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    try:
        resolved = p.resolve()
        data_root = Path("data").resolve()
        from data_ingestion_service.runs import data_root as dr

        allowed_roots = [data_root, dr()]
        ok = any(str(resolved).startswith(str(r)) for r in allowed_roots)
        ok = ok or "source_cache" in resolved.parts or "runs" in resolved.parts
        # real mode: only source_cache PDFs (trusted downloads), not random demo files
        if acq_mode == "real" and "source_cache" not in resolved.parts:
            # still allow run-local cache under data/runs
            if "runs" not in resolved.parts:
                logger.warning("local_path_rejected_real_mode", path=str(resolved))
                return None
        if not ok:
            logger.warning("local_path_rejected", path=str(resolved))
            return None
    except Exception:
        return None
    return p.read_bytes()


def _run_local_and_update(payload: dict[str, Any]) -> None:
    """Background worker: run pipeline with live stage progress into _JOBS."""
    job_id = str(payload.get("job_id") or "")
    run_id = str(payload.get("run_id") or "")

    def on_progress(stage: str, stages: dict[str, Any]) -> None:
        progress = stage_progress(stages, "processing")
        _update_job(
            job_id,
            {
                "status": "processing",
                "progress": progress,
                "result": {
                    "status": "processing",
                    "stages": stages,
                    "current_stage": stage,
                },
            },
        )
        if run_id:
            from data_ingestion_service.runs import get_run

            ctx = get_run(run_id)
            if ctx:
                ctx.append_event(
                    "stage",
                    {"job_id": job_id, "stage": stage, "percent": progress.get("percent")},
                )

    try:
        result = _run_local(payload, on_progress=on_progress)
        progress = stage_progress(result.get("stages") or {}, result.get("status"))
        _update_job(
            job_id,
            {
                "status": result.get("status", "failed"),
                "result": result,
                "progress": progress,
            },
        )
        logger.info(
            "local_ingest_done",
            job_id=job_id,
            run_id=run_id,
            acq_mode=payload.get("acq_mode"),
            status=result.get("status"),
            source_url=payload.get("source_url"),
        )
    except Exception as exc:
        logger.exception("local_ingest_failed", job_id=job_id, error=str(exc))
        _update_job(
            job_id,
            {
                "status": "failed",
                "result": {"error": str(exc), "status": "failed"},
                "progress": stage_progress({}, "failed"),
                "error": str(exc),
            },
        )


def _run_local(
    payload: dict[str, Any],
    *,
    on_progress: Any | None = None,
) -> dict[str, Any]:
    from data_kernel.pipeline.ingest_pipeline import IngestPipeline, IngestRequest
    from data_kernel.storage.object_store import build_object_store
    from data_ingestion_service.runs import get_run

    run_id = payload.get("run_id")
    acq_mode = str(payload.get("acq_mode") or "real")
    local_root = os.getenv("LAKEHOUSE_ROOT", "./data/lakehouse")
    table_root = os.getenv("LAKEHOUSE_TABLE_ROOT", "./data/lakehouse/tables")
    if run_id:
        ctx = get_run(str(run_id))
        if ctx:
            local_root = str(ctx.lakehouse_objects)
            table_root = str(ctx.lakehouse_tables)

    # Always isolate run data on local_fs (no shared MinIO mixing demo/real)
    store = build_object_store(
        minio_endpoint=os.getenv("MINIO_ENDPOINT", "http://localhost:9000"),
        minio_access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
        minio_secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin_secret"),
        local_root=local_root,
        prefer="local",
    )
    from data_kernel.lakehouse.writer import LakehouseWriter

    writer = LakehouseWriter(store, table_root=table_root)
    indexer = _get_indexer()
    pipeline = IngestPipeline(
        store=store,
        writer=writer,
        indexer=indexer,
        index_on_curate=_index_on_ingest_enabled() and indexer is not None,
        index_required=os.getenv("INDEX_REQUIRED", "false").lower()
        in ("1", "true", "yes"),
    )
    local_bytes = _load_local_bytes(payload.get("local_path"), acq_mode=acq_mode)
    # Real mode: never pass inline mock content
    content = payload.get("content") if acq_mode == "demo" else None
    req = IngestRequest(
        source_url=payload["source_url"],
        source_type=payload.get("source_type", "web"),
        license=payload.get("license", "unknown"),
        content=content,
        content_bytes=local_bytes,
        job_id=payload.get("job_id"),
        skip_robots=bool(local_bytes or content) or acq_mode == "demo",
    )
    result = pipeline.run(req, on_progress=on_progress)
    stages = dict(result.stages) if result.stages is not None else {}
    return {
        "job_id": result.job_id,
        "status": result.status,
        "stages": stages,
        "raw_uri": result.raw_uri,
        "curated_uri": result.curated_uri,
        "quarantine_uri": result.quarantine_uri,
        "manifest_id": result.manifest_id,
        "content_hash": result.content_hash,
        "error": result.error,
        "language": result.language,
        "chunk_count": result.chunk_count,
        "mode": "local",
        "acq_mode": acq_mode,
        "run_id": run_id,
        "provider": payload.get("provider"),
        "title": payload.get("title"),
        "lakehouse_objects": local_root,
        "lakehouse_tables": table_root,
    }


async def _start_temporal(
    payload: dict[str, Any],
    *,
    workflow_name: str = "IngestionWorkflow",
) -> dict[str, Any]:
    from temporalio.client import Client

    settings = _settings()
    address = os.getenv("TEMPORAL_ADDRESS") or (
        settings.temporal_address if settings else "localhost:7233"
    )
    client = await Client.connect(address)
    workflow_id = f"ingest-{payload['job_id']}"

    # Prefer typed workflow handle when worker package is importable
    run_fn = None
    try:
        from curation_worker import worker as cw

        _map = {
            "IngestionWorkflow": getattr(cw, "IngestionWorkflow", None),
            "IngestWorkflow": getattr(cw, "IngestWorkflow", None),
            "CurationWorkflow": getattr(cw, "CurationWorkflow", None),
            "IndexWorkflow": getattr(cw, "IndexWorkflow", None),
            "IngestWebWorkflow": getattr(cw, "IngestWebWorkflow", None),
            "IngestPdfWorkflow": getattr(cw, "IngestPdfWorkflow", None),
            "GraphBuildWorkflow": getattr(cw, "GraphBuildWorkflow", None),
            "CurationFilterWorkflow": getattr(cw, "CurationFilterWorkflow", None),
        }
        cls = _map.get(workflow_name) or _map.get("IngestionWorkflow")
        if cls is not None:
            run_fn = cls.run
    except Exception:
        run_fn = None

    if run_fn is not None:
        handle = await client.start_workflow(
            run_fn,
            payload,
            id=workflow_id,
            task_queue="agrimind-ingestion",
        )
    else:
        handle = await client.start_workflow(
            workflow_name,
            payload,
            id=workflow_id,
            task_queue="agrimind-ingestion",
        )
    return {
        "status": "workflow_started",
        "workflow_id": handle.id,
        "run_id": handle.result_run_id,
        "temporal": address,
        "workflow": workflow_name,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8007)
