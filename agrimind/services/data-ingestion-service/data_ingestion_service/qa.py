"""QA dashboard aggregations for Data Acquisition Plane transparency."""

from __future__ import annotations

import os
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from data_kernel.lakehouse.writer import LAKEHOUSE_TABLES, LakehouseWriter
from data_kernel.storage.object_store import ObjectStore, build_object_store

# Ordered stages for progress % (maps to IngestPipeline stage keys)
PIPELINE_STAGE_ORDER = [
    "allow_list",
    "license",
    "robots",
    "download",
    "raw_write",
    "normalize",
    "pii",
    "toxicity",
    "relevance",
    "dedup",
    "quality",
    "provenance",
    "curated_write",
    "chunks_write",
    "index",
    "manifest",
]

TERMINAL_OK = frozenset({"curated", "image_stored"})
TERMINAL_BAD = frozenset({"quarantine", "failed"})
ACTIVE = frozenset({"queued", "processing", "running", "accepted"})

# Map download/pipeline errors to stable failure classes for reports
_FAILURE_CLASS_RULES: list[tuple[str, str]] = [
    ("payload_exceeds_size_limit", "size_limit"),
    ("timed out", "timeout"),
    ("timeout", "timeout"),
    ("403", "http_forbidden"),
    ("404", "http_not_found"),
    ("503", "http_unavailable"),
    ("getaddrinfo", "dns_failed"),
    ("toxicity", "toxicity_blocked"),
    ("low_agriculture_relevance", "low_relevance"),
    ("source_not_allow_listed", "not_allow_listed"),
    ("robots", "robots_denied"),
    ("duplicate", "duplicate"),
    ("download_failed", "download_failed"),
]


def classify_failure(error: str | None, status: str | None = None) -> str | None:
    if status in TERMINAL_OK:
        return None
    if not error and status in ("quarantine", "failed"):
        return status or "failed"
    err = (error or "").lower()
    for needle, cls in _FAILURE_CLASS_RULES:
        if needle.lower() in err:
            return cls
    if status == "quarantine":
        return "quarantine"
    if status == "failed":
        return "failed"
    return None


def build_store(
    *,
    local_root: str | None = None,
    prefer: str | None = None,
) -> ObjectStore:
    return build_object_store(
        minio_endpoint=os.getenv("MINIO_ENDPOINT", "http://localhost:9000"),
        minio_access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
        minio_secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin_secret"),
        local_root=local_root or os.getenv("LAKEHOUSE_ROOT", "./data/lakehouse"),
        prefer=prefer or os.getenv("OBJECT_STORE", "local"),
    )


def build_writer(
    store: ObjectStore | None = None,
    *,
    local_root: str | None = None,
    table_root: str | None = None,
    prefer: str | None = None,
) -> LakehouseWriter:
    store = store or build_store(local_root=local_root, prefer=prefer)
    root = table_root or os.getenv("LAKEHOUSE_TABLE_ROOT", "./data/lakehouse/tables")
    return LakehouseWriter(store, table_root=root)


def build_dashboard_for_jobs(
    jobs: list[dict[str, Any]],
    *,
    local_root: str | None = None,
    table_root: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Dashboard scoped to a run's lakehouse paths when provided."""
    # Temporarily point env-backed helpers via explicit writer path
    if local_root or table_root:
        # Patch build_writer used inside build_dashboard by setting env for this call
        prev_lr = os.environ.get("LAKEHOUSE_ROOT")
        prev_tr = os.environ.get("LAKEHOUSE_TABLE_ROOT")
        prev_os = os.environ.get("OBJECT_STORE")
        try:
            if local_root:
                os.environ["LAKEHOUSE_ROOT"] = local_root
            if table_root:
                os.environ["LAKEHOUSE_TABLE_ROOT"] = table_root
            os.environ["OBJECT_STORE"] = "local"
            dash = build_dashboard(jobs)
        finally:
            if prev_lr is None:
                os.environ.pop("LAKEHOUSE_ROOT", None)
            else:
                os.environ["LAKEHOUSE_ROOT"] = prev_lr
            if prev_tr is None:
                os.environ.pop("LAKEHOUSE_TABLE_ROOT", None)
            else:
                os.environ["LAKEHOUSE_TABLE_ROOT"] = prev_tr
            if prev_os is None:
                os.environ.pop("OBJECT_STORE", None)
            else:
                os.environ["OBJECT_STORE"] = prev_os
    else:
        dash = build_dashboard(jobs)
    if extra:
        dash = {**dash, **extra}
    return dash


def _stage_ok(data: Any) -> bool:
    """A stage entry with ok=False (e.g. failed download) is not success."""
    if isinstance(data, dict) and data.get("ok") is False:
        return False
    return True


def stage_progress(stages: dict[str, Any] | None, status: str | None = None) -> dict[str, Any]:
    """Compute percent complete + stage checklist from pipeline stages dict."""
    stages = stages or {}
    completed: list[str] = []
    failed_stage: str | None = None
    details: list[dict[str, Any]] = []
    for name in PIPELINE_STAGE_ORDER:
        if name in stages:
            data = stages[name]
            ok = _stage_ok(data)
            if ok:
                completed.append(name)
            else:
                failed_stage = name
            details.append({"stage": name, "done": ok, "failed": not ok, "data": data})
        else:
            details.append({"stage": name, "done": False, "failed": False, "data": None})
    total = len(PIPELINE_STAGE_ORDER)
    done_n = len(completed)
    # Success terminals only → 100%. Failed/quarantine never show 100%.
    if status in TERMINAL_OK:
        pct = 100.0
    else:
        pct = round(100.0 * done_n / total, 1) if total else 0.0
        if status in TERMINAL_BAD or failed_stage:
            # Cap so UI never shows "100% · download" on hard failures
            pct = min(pct, 99.0)
            if status == "failed" and done_n == 0:
                pct = 0.0
    if failed_stage:
        current = failed_stage
    elif status in TERMINAL_OK:
        current = completed[-1] if completed else "curated"
    elif status == "failed":
        current = failed_stage or (completed[-1] if completed else "failed")
    else:
        current = completed[-1] if completed else "queued"
    return {
        "percent": pct,
        "completed_count": done_n,
        "total_stages": total,
        "current_stage": current,
        "completed_stages": completed,
        "failed_stage": failed_stage,
        "partial": status in TERMINAL_BAD or bool(failed_stage),
        "checklist": details,
    }


def enrich_job(job: dict[str, Any]) -> dict[str, Any]:
    """Attach progress + stage summary for UI."""
    result = job.get("result") or {}
    stages = result.get("stages") if isinstance(result, dict) else None
    if not stages and isinstance(result, dict):
        stages = (result.get("curation") or {}).get("stages")
    status = job.get("status") or (result.get("status") if isinstance(result, dict) else None)
    progress = stage_progress(stages if isinstance(stages, dict) else {}, status)
    quality = None
    language = None
    dedup = None
    pii = None
    toxicity = None
    relevance = None
    if isinstance(stages, dict):
        quality = (stages.get("quality") or {}).get("score")
        language = (stages.get("normalize") or {}).get("language")
        dedup = stages.get("dedup")
        pii = stages.get("pii")
        toxicity = stages.get("toxicity")
        relevance = stages.get("relevance")
    error = None
    if isinstance(result, dict):
        error = result.get("error") or job.get("error")
    # surface download stage error when top-level error missing
    if not error and isinstance(stages, dict):
        dl = stages.get("download")
        if isinstance(dl, dict) and dl.get("ok") is False:
            error = dl.get("error") or "download_failed"
    failure_class = classify_failure(str(error) if error else None, status)
    stage_names = [k for k in PIPELINE_STAGE_ORDER if isinstance(stages, dict) and k in stages]
    return {
        **job,
        "progress": progress,
        "failure_class": failure_class,
        "stages_completed": stage_names,
        "qa_summary": {
            "status": status,
            "quality_score": quality,
            "language": language,
            "pii_redacted": (pii or {}).get("redacted") if isinstance(pii, dict) else None,
            "toxicity_safe": (toxicity or {}).get("is_safe") if isinstance(toxicity, dict) else None,
            "relevance_score": (relevance or {}).get("score") if isinstance(relevance, dict) else None,
            "is_duplicate": (dedup or {}).get("is_duplicate") if isinstance(dedup, dict) else None,
            "dedup_reason": (dedup or {}).get("reason") if isinstance(dedup, dict) else None,
            "error": error,
            "failure_class": failure_class,
            "partial": bool(progress.get("partial")),
            "failed_stage": progress.get("failed_stage"),
            "manifest_id": result.get("manifest_id") if isinstance(result, dict) else None,
            "content_hash": result.get("content_hash") if isinstance(result, dict) else None,
            "chunk_count": result.get("chunk_count") if isinstance(result, dict) else None,
            "raw_uri": result.get("raw_uri") if isinstance(result, dict) else None,
            "curated_uri": result.get("curated_uri") if isinstance(result, dict) else None,
            "quarantine_uri": result.get("quarantine_uri") if isinstance(result, dict) else None,
        },
    }


def _bytes_from_rows(rows: list[dict[str, Any]]) -> int:
    total = 0
    for r in rows:
        sb = r.get("size_bytes")
        if isinstance(sb, int):
            total += sb
            continue
        preview = r.get("content_preview") or ""
        if preview:
            total += len(str(preview).encode("utf-8"))
    return total


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def lakehouse_snapshot(writer: LakehouseWriter, limit: int = 5000) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for t in LAKEHOUSE_TABLES:
        out[t] = writer.query_table(t, limit=limit)
    return out


def build_dashboard(
    jobs: list[dict[str, Any]],
    *,
    table_limit: int = 5000,
) -> dict[str, Any]:
    writer = build_writer()
    snap = lakehouse_snapshot(writer, limit=table_limit)

    raw = snap.get("raw.documents") or []
    curated = snap.get("curated.documents") or []
    chunks = snap.get("curated.chunks") or []
    images = snap.get("curated.images") or []
    quarantine = snap.get("quarantine.records") or []
    manifests = snap.get("manifests.datasets") or []
    models = snap.get("manifests.models") or []
    telemetry = snap.get("telemetry.events") or []

    # Job status breakdown
    status_counts: Counter[str] = Counter()
    for j in jobs:
        status_counts[str(j.get("status") or "unknown")] += 1

    # Quarantine reasons
    q_reasons: Counter[str] = Counter()
    for r in quarantine:
        q_reasons[str(r.get("quarantine_reason") or "unknown")] += 1

    # Dedup from quarantine + telemetry
    dup_n = sum(1 for r in quarantine if str(r.get("quarantine_reason") or "").startswith("duplicate"))
    # quality scores on curated
    quality_scores = [
        float(r["quality_score"])
        for r in curated
        if isinstance(r.get("quality_score"), (int, float))
    ]
    relevance_scores = [
        float(r["agriculture_relevance_score"])
        for r in curated
        if isinstance(r.get("agriculture_relevance_score"), (int, float))
    ]
    pii_n = sum(1 for r in curated if r.get("pii_redacted"))
    langs: Counter[str] = Counter(str(r.get("language") or "unknown") for r in curated)
    source_types: Counter[str] = Counter(str(r.get("source_type") or "unknown") for r in curated + raw)

    total_processed = len(raw) or (status_counts.total() or 1)
    curated_n = len(curated)
    quarantine_n = len(quarantine)
    # success rate among curated+quarantine lake rows
    lake_outcomes = curated_n + quarantine_n
    success_pct = round(100.0 * curated_n / lake_outcomes, 1) if lake_outcomes else 0.0
    quarantine_pct = round(100.0 * quarantine_n / lake_outcomes, 1) if lake_outcomes else 0.0
    dup_pct = round(100.0 * dup_n / lake_outcomes, 1) if lake_outcomes else 0.0

    curated_bytes = _bytes_from_rows(curated)
    raw_bytes = _bytes_from_rows(raw)
    image_bytes = _bytes_from_rows(images)
    chunk_bytes = sum(len(str(c.get("text") or c.get("content") or "").encode("utf-8")) for c in chunks)

    ready_corpus_bytes = curated_bytes + chunk_bytes + image_bytes
    avg_quality = _avg(quality_scores)
    avg_relevance = _avg(relevance_scores)

    # Quality tiers for QA
    high_q = sum(1 for s in quality_scores if s >= 0.75)
    med_q = sum(1 for s in quality_scores if 0.5 <= s < 0.75)
    low_q = sum(1 for s in quality_scores if s < 0.5)

    # Recent jobs enriched
    recent_jobs = [enrich_job(j) for j in jobs[-30:]][::-1]

    # Health
    store = writer.store
    backend = getattr(store, "backend", "unknown")

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "service": "data-ingestion-service",
        "store_backend": backend,
        "pipeline_stages": PIPELINE_STAGE_ORDER,
        "lakehouse_tables": list(LAKEHOUSE_TABLES),
        "kpis": {
            "jobs_total": len(jobs),
            "jobs_by_status": dict(status_counts),
            "raw_documents": len(raw),
            "curated_documents": curated_n,
            "curated_chunks": len(chunks),
            "curated_images": len(images),
            "quarantine_records": quarantine_n,
            "duplicates_detected": dup_n,
            "manifests": len(manifests),
            "model_manifests": len(models),
            "telemetry_events": len(telemetry),
            "success_rate_pct": success_pct,
            "quarantine_rate_pct": quarantine_pct,
            "duplicate_rate_pct": dup_pct,
            "avg_quality_score": avg_quality,
            "avg_relevance_score": avg_relevance,
            "pii_redacted_docs": pii_n,
            "ready_corpus_records": curated_n + len(chunks) + len(images),
            "ready_corpus_bytes": ready_corpus_bytes,
            "raw_bytes": raw_bytes,
            "curated_bytes": curated_bytes,
            "image_bytes": image_bytes,
        },
        "quality_distribution": {
            "high_gte_0_75": high_q,
            "medium_0_5_to_0_75": med_q,
            "low_lt_0_5": low_q,
            "scored": len(quality_scores),
        },
        "languages": dict(langs),
        "source_types": dict(source_types),
        "quarantine_reasons": dict(q_reasons.most_common(20)),
        "corpus": {
            "status": "ready" if curated_n > 0 else "empty",
            "documents": curated_n,
            "chunks": len(chunks),
            "images": len(images),
            "total_records": curated_n + len(chunks) + len(images),
            "size_bytes": ready_corpus_bytes,
            "size_human": _human_bytes(ready_corpus_bytes),
            "avg_quality": avg_quality,
            "languages": dict(langs),
            "manifests": len(manifests),
            "latest_manifest_id": manifests[-1].get("manifest_id") if manifests else None,
        },
        "recent_jobs": recent_jobs,
        "tables_counts": {t: len(snap.get(t) or []) for t in LAKEHOUSE_TABLES},
    }


def build_report(
    jobs: list[dict[str, Any]],
    *,
    include_samples: bool = True,
    sample_limit: int = 25,
) -> dict[str, Any]:
    writer = build_writer()
    dash = build_dashboard(jobs)
    curated = writer.query_table("curated.documents", limit=sample_limit)
    quarantine = writer.query_table("quarantine.records", limit=sample_limit)
    chunks = writer.query_table("curated.chunks", limit=sample_limit)
    images = writer.query_table("curated.images", limit=sample_limit)
    manifests = writer.list_manifests(limit=sample_limit)
    telemetry = writer.query_table("telemetry.events", limit=sample_limit)

    samples: dict[str, Any] = {}
    if include_samples:
        samples = {
            "curated_documents": [_safe_row(r) for r in curated],
            "quarantine_records": [_safe_row(r) for r in quarantine],
            "curated_chunks": [_safe_row(r, text_keys=("text", "content")) for r in chunks],
            "curated_images": [_safe_row(r) for r in images],
            "manifests": manifests,
            "telemetry": telemetry[-sample_limit:],
        }

    # QA checklist (transparent gates)
    k = dash["kpis"]
    checklist = [
        {
            "id": "pipeline_e2e",
            "label": "Ingestion pipeline produces curated or quarantine outcomes",
            "pass": (k["curated_documents"] + k["quarantine_records"]) > 0 or k["jobs_total"] > 0,
        },
        {
            "id": "provenance",
            "label": "Curated records include provenance / checksum",
            "pass": all(
                bool(r.get("content_hash") or (r.get("provenance") or {}).get("checksum"))
                for r in curated
            )
            if curated
            else True,
        },
        {
            "id": "pii_path",
            "label": "PII redaction path exercised or no PII flagged",
            "pass": True,  # informational; pii count tracked separately
            "info": f"pii_redacted_docs={k['pii_redacted_docs']}",
        },
        {
            "id": "quarantine_path",
            "label": "Quarantine table queryable",
            "pass": True,
            "info": f"records={k['quarantine_records']}",
        },
        {
            "id": "manifests",
            "label": "Dataset manifests queryable",
            "pass": k["manifests"] >= 0,
            "info": f"count={k['manifests']}",
        },
        {
            "id": "quality_scores",
            "label": "Quality scores present on curated docs",
            "pass": dash["quality_distribution"]["scored"] == k["curated_documents"]
            if k["curated_documents"]
            else True,
        },
        {
            "id": "corpus_ready",
            "label": "Ready corpus has documents or chunks",
            "pass": dash["corpus"]["total_records"] > 0,
            "info": dash["corpus"]["size_human"],
        },
    ]
    passed = sum(1 for c in checklist if c["pass"])
    return {
        "report_id": f"qa-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}",
        "generated_at": datetime.now(UTC).isoformat(),
        "dashboard": dash,
        "qa_checklist": checklist,
        "qa_score_pct": round(100.0 * passed / len(checklist), 1) if checklist else 0.0,
        "samples": samples,
        "recommendations": _recommendations(dash),
    }


def corpus_detail(
    limit: int = 100,
    *,
    local_root: str | None = None,
    table_root: str | None = None,
) -> dict[str, Any]:
    writer = build_writer(local_root=local_root, table_root=table_root, prefer="local")
    curated = writer.query_table("curated.documents", limit=limit)
    chunks = writer.query_table("curated.chunks", limit=limit)
    images = writer.query_table("curated.images", limit=limit)
    manifests = writer.list_manifests(limit=50)

    docs = []
    for r in curated:
        docs.append(
            {
                "document_id": r.get("document_id"),
                "job_id": r.get("job_id"),
                "source_url": r.get("source_url"),
                "source_type": r.get("source_type"),
                "language": r.get("language"),
                "quality_score": r.get("quality_score"),
                "relevance_score": r.get("agriculture_relevance_score"),
                "pii_redacted": r.get("pii_redacted"),
                "content_hash": r.get("content_hash"),
                "size_bytes": r.get("size_bytes")
                or len(str(r.get("content_preview") or "").encode("utf-8")),
                "object_uri": r.get("object_uri"),
                "manifest_hint": (r.get("provenance") or {}).get("source_id"),
                "license": r.get("license") or r.get("license_type"),
                "curated_at": r.get("curated_at"),
                "preview": (r.get("content_preview") or "")[:240],
                "provenance": r.get("provenance"),
            }
        )

    size = sum(int(d.get("size_bytes") or 0) for d in docs)
    size += sum(len(str(c.get("text") or c.get("content") or "").encode("utf-8")) for c in chunks)
    size += _bytes_from_rows(images)

    return {
        "status": "ready" if docs or chunks or images else "empty",
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": {
            "documents": len(docs),
            "chunks": len(chunks),
            "images": len(images),
            "total_records": len(docs) + len(chunks) + len(images),
            "size_bytes": size,
            "size_human": _human_bytes(size),
            "manifests": len(manifests),
        },
        "documents": docs,
        "chunks_sample": [
            {
                "document_id": c.get("document_id"),
                "chunk_index": c.get("chunk_index"),
                "chars": len(str(c.get("text") or c.get("content") or "")),
                "lang": c.get("lang") or c.get("language"),
                "preview": str(c.get("text") or c.get("content") or "")[:160],
            }
            for c in chunks[:limit]
        ],
        "images": [
            {
                "document_id": i.get("document_id"),
                "source_url": i.get("source_url"),
                "size_bytes": i.get("size_bytes"),
                "content_type": i.get("content_type"),
                "content_hash": i.get("content_hash"),
                "object_uri": i.get("object_uri"),
            }
            for i in images
        ],
        "manifests": manifests,
        "partial": True if docs or chunks or images else False,
        "scope": {
            "local_root": local_root,
            "table_root": table_root,
        },
    }


def build_run_failure_report(
    jobs: list[dict[str, Any]],
    *,
    run_id: str | None = None,
    acq_mode: str | None = None,
    local_root: str | None = None,
    table_root: str | None = None,
) -> dict[str, Any]:
    """Tracking report for partial/failed runs: classes, job details, partial corpus KPIs."""
    enriched = [enrich_job(j) for j in jobs]
    by_status: Counter[str] = Counter(str(j.get("status") or "unknown") for j in enriched)
    failed_jobs = [j for j in enriched if j.get("status") in ("failed", "quarantine")]
    ok_jobs = [j for j in enriched if j.get("status") in TERMINAL_OK]
    active = [j for j in enriched if j.get("status") in ACTIVE]

    class_counts: Counter[str] = Counter()
    failure_rows: list[dict[str, Any]] = []
    for j in failed_jobs:
        qs = j.get("qa_summary") or {}
        err = qs.get("error") or j.get("error")
        cls = j.get("failure_class") or classify_failure(
            str(err) if err else None, str(j.get("status"))
        )
        class_counts[str(cls or "unknown")] += 1
        failure_rows.append(
            {
                "job_id": j.get("job_id"),
                "status": j.get("status"),
                "failure_class": cls,
                "error": err,
                "source_url": j.get("source_url"),
                "source_type": j.get("source_type"),
                "title": j.get("title") or j.get("provider"),
                "provider": j.get("provider"),
                "progress_percent": (j.get("progress") or {}).get("percent"),
                "failed_stage": (j.get("progress") or {}).get("failed_stage")
                or qs.get("failed_stage"),
                "stages_completed": j.get("stages_completed")
                or (j.get("progress") or {}).get("completed_stages"),
                "raw_uri": qs.get("raw_uri"),
                "quarantine_uri": qs.get("quarantine_uri"),
                "updated_at": j.get("updated_at"),
            }
        )

    # Partial corpus from run lakehouse (curated docs that did pass)
    corp = corpus_detail(
        limit=200, local_root=local_root, table_root=table_root
    )
    total = max(len(enriched), 1)
    success_n = len(ok_jobs)
    fail_n = len(failed_jobs)
    partial = success_n > 0 and fail_n > 0
    outcome = (
        "success"
        if fail_n == 0 and success_n > 0 and not active
        else "failed"
        if success_n == 0 and fail_n > 0 and not active
        else "partial"
        if partial or active
        else "empty"
    )

    recommendations: list[str] = []
    if class_counts.get("http_not_found"):
        recommendations.append(
            "Some catalog URLs returned 404 — update seed catalog / discovery hits."
        )
    if class_counts.get("timeout") or class_counts.get("dns_failed"):
        recommendations.append(
            "Network timeouts/DNS failures — retry later or use source_cache PDFs."
        )
    if class_counts.get("size_limit"):
        recommendations.append(
            "PDF size limit hit — prefer smaller docs or increase PDF max_bytes."
        )
    if class_counts.get("toxicity_blocked"):
        recommendations.append(
            "Toxicity false positives possible on long agri PDFs — review filter."
        )
    if class_counts.get("low_relevance"):
        recommendations.append(
            "Low agri relevance — prefer domain pages with crop/soil content."
        )
    if partial:
        recommendations.append(
            f"Partial success: {success_n}/{total} jobs curated — use partial corpus."
        )
    if not recommendations:
        recommendations.append("No failures classified — review raw job errors.")

    return {
        "report_id": f"fail-{run_id or 'global'}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}",
        "generated_at": datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "acq_mode": acq_mode,
        "outcome": outcome,
        "partial": partial or outcome == "partial",
        "summary": {
            "jobs_total": len(enriched),
            "jobs_by_status": dict(by_status),
            "success_count": success_n,
            "failed_or_quarantine": fail_n,
            "active_count": len(active),
            "success_rate_pct": round(100.0 * success_n / total, 1),
            "failure_classes": dict(class_counts.most_common()),
        },
        "failures": sorted(
            failure_rows,
            key=lambda r: (str(r.get("failure_class") or ""), str(r.get("job_id") or "")),
        ),
        "success_jobs": [
            {
                "job_id": j.get("job_id"),
                "source_url": j.get("source_url"),
                "title": j.get("title"),
                "chunk_count": (j.get("qa_summary") or {}).get("chunk_count")
                or (j.get("result") or {}).get("chunk_count"),
                "manifest_id": (j.get("qa_summary") or {}).get("manifest_id")
                or (j.get("result") or {}).get("manifest_id"),
                "language": (j.get("qa_summary") or {}).get("language"),
            }
            for j in ok_jobs
        ],
        "partial_corpus": {
            "status": corp.get("status"),
            "summary": corp.get("summary"),
            "documents_sample": (corp.get("documents") or [])[:15],
            "chunks_sample": (corp.get("chunks_sample") or [])[:10],
        },
        "recommendations": recommendations,
        "paths": {"local_root": local_root, "table_root": table_root},
    }


def quarantine_detail(limit: int = 100) -> dict[str, Any]:
    writer = build_writer()
    rows = writer.query_table("quarantine.records", limit=limit)
    reasons: Counter[str] = Counter(str(r.get("quarantine_reason") or "unknown") for r in rows)
    items = []
    for r in rows:
        reason = str(r.get("quarantine_reason") or "")
        items.append(
            {
                "document_id": r.get("document_id"),
                "job_id": r.get("job_id"),
                "source_url": r.get("source_url"),
                "source_type": r.get("source_type"),
                "reason": reason,
                "is_duplicate": reason.startswith("duplicate"),
                "duplicate_of": r.get("duplicate_of"),
                "quality_score": r.get("quality_score"),
                "object_uri": r.get("object_uri"),
                "quarantined_at": r.get("quarantined_at"),
                "license": r.get("license"),
            }
        )
    return {
        "count": len(items),
        "reasons": dict(reasons.most_common()),
        "duplicate_count": sum(1 for i in items if i["is_duplicate"]),
        "records": items,
        "generated_at": datetime.now(UTC).isoformat(),
    }


def quality_detail(limit: int = 100) -> dict[str, Any]:
    writer = build_writer()
    curated = writer.query_table("curated.documents", limit=limit)
    rows = []
    for r in curated:
        q = r.get("quality_score")
        tier = "unscored"
        if isinstance(q, (int, float)):
            if q >= 0.75:
                tier = "high"
            elif q >= 0.5:
                tier = "medium"
            else:
                tier = "low"
        rows.append(
            {
                "document_id": r.get("document_id"),
                "source_url": r.get("source_url"),
                "quality_score": q,
                "tier": tier,
                "relevance_score": r.get("agriculture_relevance_score"),
                "language": r.get("language"),
                "pii_redacted": r.get("pii_redacted"),
                "toxicity_score": r.get("toxicity_score"),
                "content_hash": r.get("content_hash"),
                "preview": (r.get("content_preview") or "")[:200],
            }
        )
    tiers = Counter(r["tier"] for r in rows)
    return {
        "count": len(rows),
        "tiers": dict(tiers),
        "avg_quality": _avg(
            [float(r["quality_score"]) for r in rows if isinstance(r.get("quality_score"), (int, float))]
        ),
        "records": sorted(
            rows,
            key=lambda x: (x.get("quality_score") is not None, x.get("quality_score") or 0),
            reverse=True,
        ),
        "generated_at": datetime.now(UTC).isoformat(),
    }


def _human_bytes(n: int) -> str:
    x = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if abs(x) < 1024:
            return f"{x:.1f} {unit}" if unit != "B" else f"{int(x)} B"
        x /= 1024
    return f"{x:.2f} TB"


def _safe_row(r: dict[str, Any], text_keys: tuple[str, ...] = ()) -> dict[str, Any]:
    out = dict(r)
    for k in text_keys:
        if k in out and isinstance(out[k], str) and len(out[k]) > 300:
            out[k] = out[k][:300] + "…"
    if "content_preview" in out and isinstance(out["content_preview"], str):
        out["content_preview"] = out["content_preview"][:300]
    return out


def _recommendations(dash: dict[str, Any]) -> list[str]:
    recs: list[str] = []
    k = dash["kpis"]
    if k["curated_documents"] == 0:
        recs.append("No curated corpus yet — run sample ingest jobs from the Ingest tab.")
    if k["quarantine_rate_pct"] and k["quarantine_rate_pct"] > 40:
        recs.append(
            f"Quarantine rate is high ({k['quarantine_rate_pct']}%). "
            "Review allow-list, licenses, and relevance thresholds."
        )
    if k["duplicate_rate_pct"] and k["duplicate_rate_pct"] > 15:
        recs.append(
            f"Duplicate rate {k['duplicate_rate_pct']}% — near-dup MinHash is catching re-ingests; "
            "expected for QA re-runs."
        )
    if k.get("avg_quality_score") is not None and k["avg_quality_score"] < 0.5:
        recs.append("Average quality score below 0.5 — prefer longer agri-relevant source content.")
    if not recs:
        recs.append("Corpus looks healthy. Export the QA report for audit trail.")
    return recs
