"""Run-scoped data acquisition foundation: demo vs real isolation + cleanup.

Layout under DATA_ROOT (default ./data)::

    data/
      runs/
        {run_id}/
          meta.json              # run header (mode, status, counts)
          process.jsonl          # stage / job events (append-only)
          jobs/
            {job_id}.json        # full job snapshot
          lakehouse/
            objects/             # object store (LocalObjectStore root)
            tables/              # JSONL lake tables
      demo/                      # optional shared demo workspace (legacy)
      lakehouse/                 # legacy shared (migrated away for new runs)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

AcqMode = Literal["demo", "real"]

_RUNS_LOCK = threading.Lock()
_ACTIVE_RUNS: dict[str, "RunContext"] = {}

# Hosts / URL patterns forbidden in real mode
_REAL_BLOCK_HOSTS = (
    "example.com",
    "example.net",
    "example.org",
    "localhost",
    "127.0.0.1",
)
_REAL_BLOCK_URL_SUBSTR = (
    "/demo/",
    "demo:",
    "evil.example",
)


def data_root() -> Path:
    root = os.getenv("DATA_ROOT") or os.getenv("AGRIMIND_DATA_ROOT")
    if root:
        return Path(root).resolve()
    # default: agrimind/data when cwd is agrimind
    return Path(os.getenv("LAKEHOUSE_ROOT", "./data/lakehouse")).resolve().parent


def runs_root() -> Path:
    p = data_root() / "runs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def new_run_id(mode: AcqMode) -> str:
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    short = uuid.uuid4().hex[:8]
    return f"{mode}-{ts}-{short}"


def is_demo_url(url: str) -> bool:
    u = (url or "").lower().strip()
    if not u:
        return True
    if any(b in u for b in _REAL_BLOCK_URL_SUBSTR):
        return True
    try:
        from urllib.parse import urlparse

        host = (urlparse(u).netloc or "").split(":")[0]
        if host in _REAL_BLOCK_HOSTS:
            return True
        if host.endswith(".example.com") or host.endswith(".example.net"):
            return True
    except Exception:
        pass
    return False


def validate_source_for_mode(
    *,
    mode: AcqMode,
    source_url: str,
    content: str | None = None,
    allow_inline_in_demo: bool = True,
) -> None:
    """Raise ValueError if source is invalid for the acquisition mode."""
    if mode == "demo":
        return
    # REAL mode rules
    if content is not None and content.strip():
        # Inline/mock content not allowed in real runs (must fetch real source)
        raise ValueError(
            "real_mode_forbids_inline_content: omit content and use a trusted live URL"
        )
    if is_demo_url(source_url):
        raise ValueError(
            f"real_mode_forbids_demo_or_example_url: {source_url!r}"
        )
    # must look like http(s)
    if not re.match(r"^https?://", source_url.strip(), re.I):
        raise ValueError("real_mode_requires_http_url")


@dataclass
class RunContext:
    run_id: str
    mode: AcqMode
    created_at: str
    status: str = "running"  # running | completed | failed | cancelled
    label: str | None = None
    job_ids: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    finished_at: str | None = None

    @property
    def root(self) -> Path:
        return runs_root() / self.run_id

    @property
    def lakehouse_objects(self) -> Path:
        return self.root / "lakehouse" / "objects"

    @property
    def lakehouse_tables(self) -> Path:
        return self.root / "lakehouse" / "tables"

    @property
    def jobs_dir(self) -> Path:
        return self.root / "jobs"

    def ensure_dirs(self) -> None:
        self.lakehouse_objects.mkdir(parents=True, exist_ok=True)
        self.lakehouse_tables.mkdir(parents=True, exist_ok=True)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)

    def meta_path(self) -> Path:
        return self.root / "meta.json"

    def process_log_path(self) -> Path:
        return self.root / "process.jsonl"

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "mode": self.mode,
            "created_at": self.created_at,
            "status": self.status,
            "label": self.label,
            "job_ids": list(self.job_ids),
            "stats": dict(self.stats),
            "error": self.error,
            "finished_at": self.finished_at,
            "paths": {
                "root": str(self.root),
                "lakehouse_objects": str(self.lakehouse_objects),
                "lakehouse_tables": str(self.lakehouse_tables),
                "jobs": str(self.jobs_dir),
                "meta": str(self.meta_path()),
                "process_log": str(self.process_log_path()),
            },
        }

    def save_meta(self) -> None:
        self.ensure_dirs()
        self.meta_path().write_text(
            json.dumps(self.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )

    def append_event(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        self.ensure_dirs()
        row = {
            "ts": datetime.now(UTC).isoformat(),
            "event": event_type,
            "run_id": self.run_id,
            "mode": self.mode,
            **(payload or {}),
        }
        with self.process_log_path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")

    def save_job_snapshot(self, job: dict[str, Any]) -> None:
        self.ensure_dirs()
        jid = str(job.get("job_id") or "unknown")
        path = self.jobs_dir / f"{jid}.json"
        path.write_text(json.dumps(job, indent=2, default=str), encoding="utf-8")

    def touch_job(self, job_id: str) -> None:
        if job_id not in self.job_ids:
            self.job_ids.append(job_id)
            self.stats["jobs_total"] = len(self.job_ids)
            self.save_meta()


def create_run(
    mode: AcqMode,
    *,
    label: str | None = None,
    run_id: str | None = None,
) -> RunContext:
    rid = run_id or new_run_id(mode)
    # sanitize
    rid = re.sub(r"[^a-zA-Z0-9._-]", "-", rid)[:80]
    ctx = RunContext(
        run_id=rid,
        mode=mode,
        created_at=datetime.now(UTC).isoformat(),
        label=label,
        stats={"jobs_total": 0, "curated": 0, "quarantine": 0, "failed": 0},
    )
    ctx.ensure_dirs()
    ctx.save_meta()
    ctx.append_event("run_created", {"label": label})
    with _RUNS_LOCK:
        _ACTIVE_RUNS[rid] = ctx
    return ctx


def get_run(run_id: str) -> RunContext | None:
    with _RUNS_LOCK:
        if run_id in _ACTIVE_RUNS:
            return _ACTIVE_RUNS[run_id]
    meta = runs_root() / run_id / "meta.json"
    if not meta.is_file():
        return None
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
        ctx = RunContext(
            run_id=data["run_id"],
            mode=data.get("mode") or "demo",
            created_at=data.get("created_at") or datetime.now(UTC).isoformat(),
            status=data.get("status") or "unknown",
            label=data.get("label"),
            job_ids=list(data.get("job_ids") or []),
            stats=dict(data.get("stats") or {}),
            error=data.get("error"),
            finished_at=data.get("finished_at"),
        )
        with _RUNS_LOCK:
            _ACTIVE_RUNS[run_id] = ctx
        return ctx
    except Exception:
        return None


def list_runs(*, mode: AcqMode | None = None, limit: int = 50) -> list[dict[str, Any]]:
    root = runs_root()
    items: list[dict[str, Any]] = []
    if not root.exists():
        return []
    for p in sorted(root.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if not p.is_dir():
            continue
        meta = p / "meta.json"
        if not meta.is_file():
            continue
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
        except Exception:
            continue
        if mode and data.get("mode") != mode:
            continue
        # disk usage hint
        try:
            size = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
        except Exception:
            size = 0
        data["size_bytes"] = size
        data["size_human"] = _human_bytes(size)
        items.append(data)
        if len(items) >= limit:
            break
    return items


def finish_run(run_id: str, status: str = "completed", error: str | None = None) -> RunContext | None:
    ctx = get_run(run_id)
    if not ctx:
        return None
    ctx.status = status
    ctx.error = error
    ctx.finished_at = datetime.now(UTC).isoformat()
    ctx.append_event("run_finished", {"status": status, "error": error})
    ctx.save_meta()
    return ctx


def update_run_stats_from_job(run_id: str, job: dict[str, Any]) -> None:
    ctx = get_run(run_id)
    if not ctx:
        return
    status = str(job.get("status") or "")
    if status == "curated":
        ctx.stats["curated"] = int(ctx.stats.get("curated") or 0) + 1
    elif status == "quarantine":
        ctx.stats["quarantine"] = int(ctx.stats.get("quarantine") or 0) + 1
    elif status == "failed":
        ctx.stats["failed"] = int(ctx.stats.get("failed") or 0) + 1
    ctx.save_job_snapshot(job)
    ctx.append_event(
        "job_updated",
        {
            "job_id": job.get("job_id"),
            "status": status,
            "progress": (job.get("progress") or {}).get("percent"),
            "source_url": job.get("source_url"),
        },
    )
    ctx.save_meta()


def read_process_log(run_id: str, limit: int = 500) -> list[dict[str, Any]]:
    ctx = get_run(run_id)
    if not ctx or not ctx.process_log_path().is_file():
        return []
    rows: list[dict[str, Any]] = []
    with ctx.process_log_path().open(encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows[-limit:]


def cleanup_run(run_id: str, *, dry_run: bool = False) -> dict[str, Any]:
    path = runs_root() / run_id
    if not path.exists():
        return {"run_id": run_id, "deleted": False, "reason": "not_found", "dry_run": dry_run}
    size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    if dry_run:
        return {
            "run_id": run_id,
            "deleted": False,
            "dry_run": True,
            "would_delete_bytes": size,
            "path": str(path),
        }
    shutil.rmtree(path, ignore_errors=True)
    with _RUNS_LOCK:
        _ACTIVE_RUNS.pop(run_id, None)
    return {
        "run_id": run_id,
        "deleted": True,
        "dry_run": False,
        "freed_bytes": size,
        "freed_human": _human_bytes(size),
        "path": str(path),
    }


def cleanup_runs(
    *,
    mode: AcqMode | None = None,
    older_than_hours: float | None = None,
    keep_latest: int = 0,
    dry_run: bool = False,
    include_legacy_lakehouse: bool = False,
) -> dict[str, Any]:
    """Delete run folders matching filters. Optionally wipe legacy shared lakehouse."""
    root = runs_root()
    now = datetime.now(UTC)
    candidates: list[tuple[Path, dict[str, Any], float]] = []
    if root.exists():
        for p in root.iterdir():
            if not p.is_dir():
                continue
            meta_path = p / "meta.json"
            meta: dict[str, Any] = {}
            if meta_path.is_file():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except Exception:
                    meta = {"run_id": p.name, "mode": "unknown"}
            else:
                meta = {"run_id": p.name, "mode": "unknown"}
            if mode and meta.get("mode") != mode:
                continue
            mtime = p.stat().st_mtime
            if older_than_hours is not None:
                age_h = (now.timestamp() - mtime) / 3600.0
                if age_h < older_than_hours:
                    continue
            candidates.append((p, meta, mtime))

    # keep newest N
    candidates.sort(key=lambda x: x[2], reverse=True)
    if keep_latest > 0:
        candidates = candidates[keep_latest:]

    results = []
    freed = 0
    for p, meta, _ in candidates:
        r = cleanup_run(str(meta.get("run_id") or p.name), dry_run=dry_run)
        results.append(r)
        freed += int(r.get("freed_bytes") or r.get("would_delete_bytes") or 0)

    legacy: dict[str, Any] | None = None
    if include_legacy_lakehouse:
        legacy = cleanup_legacy_lakehouse(dry_run=dry_run)
        freed += int(legacy.get("freed_bytes") or legacy.get("would_delete_bytes") or 0)

    return {
        "dry_run": dry_run,
        "mode_filter": mode,
        "older_than_hours": older_than_hours,
        "keep_latest": keep_latest,
        "runs_touched": len(results),
        "results": results,
        "legacy_lakehouse": legacy,
        "total_freed_bytes": freed,
        "total_freed_human": _human_bytes(freed),
    }


def cleanup_legacy_lakehouse(*, dry_run: bool = False) -> dict[str, Any]:
    """Remove shared legacy ./data/lakehouse (pre-runId layout)."""
    lake = data_root() / "lakehouse"
    if not lake.exists():
        return {"path": str(lake), "deleted": False, "reason": "not_found", "dry_run": dry_run}
    size = sum(f.stat().st_size for f in lake.rglob("*") if f.is_file())
    if dry_run:
        return {
            "path": str(lake),
            "deleted": False,
            "dry_run": True,
            "would_delete_bytes": size,
            "would_delete_human": _human_bytes(size),
        }
    shutil.rmtree(lake, ignore_errors=True)
    return {
        "path": str(lake),
        "deleted": True,
        "dry_run": False,
        "freed_bytes": size,
        "freed_human": _human_bytes(size),
    }


def _human_bytes(n: int | float) -> str:
    x = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(x) < 1024:
            return f"{x:.1f} {unit}" if unit != "B" else f"{int(x)} B"
        x /= 1024
    return f"{x:.2f} PB"
