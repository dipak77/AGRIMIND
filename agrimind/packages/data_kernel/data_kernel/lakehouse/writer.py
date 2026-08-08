"""Lakehouse writer: raw/curated/chunks/images/quarantine/manifests/telemetry (Phase 2)."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from data_kernel.storage.object_store import ObjectStore, PutResult

BUCKET_RAW = "agrimind-raw"
BUCKET_CURATED = "agrimind-curated"
BUCKET_QUARANTINE = "agrimind-quarantine"
BUCKET_MANIFESTS = "agrimind-manifests"
BUCKET_IMAGES = "agrimind-images"

LAKEHOUSE_TABLES = [
    "raw.documents",
    "curated.documents",
    "curated.chunks",
    "curated.images",
    "quarantine.records",
    "manifests.datasets",
    "manifests.models",
    "telemetry.events",
]


@dataclass
class LakehouseWrite:
    status: str
    put: PutResult
    record: dict[str, Any]
    manifest_id: str | None = None


class LakehouseWriter:
    def __init__(self, store: ObjectStore, table_root: str | Path = "./data/lakehouse/tables") -> None:
        self.store = store
        self.table_root = Path(table_root)
        self.table_root.mkdir(parents=True, exist_ok=True)

    def write_raw(
        self,
        *,
        job_id: str,
        source_url: str,
        content: bytes,
        license: str,
        source_type: str = "web",
        metadata: dict | None = None,
        source_id: str | None = None,
    ) -> LakehouseWrite:
        checksum = "sha256:" + __import__("hashlib").sha256(content).hexdigest()
        key = f"raw/{job_id}/{checksum.replace(':', '_')}.bin"
        put = self.store.put_bytes(BUCKET_RAW, key, content, content_type="application/octet-stream")
        record = {
            "job_id": job_id,
            "document_id": str(uuid.uuid4()),
            "source_id": source_id or f"src:{job_id}",
            "status": "raw",
            "source_url": source_url,
            "source_type": source_type,
            "license": license,
            "content_hash": put.checksum or checksum,
            "size_bytes": put.size_bytes,
            "object_uri": put.uri,
            "object_key": put.key,
            "bucket": put.bucket,
            "backend": put.backend,
            "ingested_at": datetime.now(UTC).isoformat(),
            "metadata": metadata or {},
            "provenance": {
                "source_url": source_url,
                "source_id": source_id or f"src:{job_id}",
                "checksum": put.checksum or checksum,
                "license": license,
            },
        }
        self._append_table("raw.documents", record)
        self.write_telemetry("raw_write", {"job_id": job_id, "uri": put.uri, "checksum": put.checksum})
        return LakehouseWrite(status="raw", put=put, record=record)

    def write_curated(self, record: dict[str, Any], content: str) -> LakehouseWrite:
        job_id = record.get("job_id") or "unknown"
        doc_id = record.get("document_id") or str(uuid.uuid4())
        data = content.encode("utf-8")
        key = f"curated/{job_id}/{doc_id}.txt"
        put = self.store.put_bytes(BUCKET_CURATED, key, data, content_type="text/plain; charset=utf-8")
        full = {
            **record,
            "status": "curated",
            "document_id": doc_id,
            "content_hash": put.checksum,
            "object_uri": put.uri,
            "object_key": put.key,
            "bucket": put.bucket,
            "backend": put.backend,
            "curated_at": datetime.now(UTC).isoformat(),
            "content_preview": content[:500],
        }
        self._append_table("curated.documents", full)
        self.write_telemetry("curated_write", {"job_id": job_id, "document_id": doc_id})
        return LakehouseWrite(status="curated", put=put, record=full)

    def write_chunks(self, chunks: list[dict[str, Any]], *, document_id: str, job_id: str) -> int:
        n = 0
        for ch in chunks:
            row = {
                **ch,
                "document_id": document_id,
                "job_id": job_id,
                "written_at": datetime.now(UTC).isoformat(),
            }
            self._append_table("curated.chunks", row)
            n += 1
        if n:
            self.write_telemetry("chunks_write", {"job_id": job_id, "document_id": document_id, "count": n})
        return n

    def write_image(
        self,
        *,
        job_id: str,
        source_url: str,
        content: bytes,
        content_type: str,
        license: str,
        metadata: dict | None = None,
    ) -> LakehouseWrite:
        checksum = "sha256:" + __import__("hashlib").sha256(content).hexdigest()
        doc_id = str(uuid.uuid4())
        ext = "bin"
        if "jpeg" in content_type or "jpg" in content_type:
            ext = "jpg"
        elif "png" in content_type:
            ext = "png"
        key = f"images/{job_id}/{doc_id}.{ext}"
        put = self.store.put_bytes(BUCKET_IMAGES, key, content, content_type=content_type)
        record = {
            "job_id": job_id,
            "document_id": doc_id,
            "source_url": source_url,
            "source_type": "image",
            "license": license,
            "content_hash": put.checksum or checksum,
            "object_uri": put.uri,
            "content_type": content_type,
            "size_bytes": put.size_bytes,
            "metadata": metadata or {},
            "written_at": datetime.now(UTC).isoformat(),
            "provenance": {
                "source_url": source_url,
                "checksum": put.checksum or checksum,
                "license": license,
            },
        }
        self._append_table("curated.images", record)
        return LakehouseWrite(status="image", put=put, record=record)

    def write_quarantine(self, record: dict[str, Any], reason: str, content: str = "") -> LakehouseWrite:
        job_id = record.get("job_id") or "unknown"
        doc_id = record.get("document_id") or str(uuid.uuid4())
        payload = json.dumps(
            {"reason": reason, "record": record, "content_preview": content[:1000]},
            ensure_ascii=False,
        ).encode("utf-8")
        key = f"quarantine/{job_id}/{doc_id}.json"
        put = self.store.put_bytes(
            BUCKET_QUARANTINE, key, payload, content_type="application/json"
        )
        full = {
            **record,
            "status": "quarantine",
            "document_id": doc_id,
            "quarantine_reason": reason,
            "object_uri": put.uri,
            "object_key": put.key,
            "bucket": put.bucket,
            "backend": put.backend,
            "quarantined_at": datetime.now(UTC).isoformat(),
        }
        self._append_table("quarantine.records", full)
        self.write_telemetry("quarantine", {"job_id": job_id, "reason": reason})
        return LakehouseWrite(status="quarantine", put=put, record=full)

    def write_dataset_manifest(
        self,
        *,
        source_ids: list[str],
        languages: list[str],
        record_count: int,
        checksum: str,
        notes: str = "",
    ) -> dict[str, Any]:
        manifest_id = f"ds-{datetime.now(UTC).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
        manifest = {
            "manifest_id": manifest_id,
            "version": "0.1.0",
            "created_at": datetime.now(UTC).isoformat(),
            "source_ids": source_ids,
            "checksum": checksum,
            "languages": languages,
            "record_count": record_count,
            "tokenizer_manifest_id": "agrimind-tokenizer-v1",
            "notes": notes,
            "tables": {t: t for t in LAKEHOUSE_TABLES},
        }
        data = json.dumps(manifest, indent=2).encode("utf-8")
        key = f"manifests/{manifest_id}.json"
        put = self.store.put_bytes(BUCKET_MANIFESTS, key, data, content_type="application/json")
        manifest["object_uri"] = put.uri
        self._append_table("manifests.datasets", manifest)
        return manifest

    def write_model_manifest(self, manifest: dict[str, Any]) -> dict[str, Any]:
        mid = manifest.get("model_id") or manifest.get("manifest_id") or str(uuid.uuid4())
        row = {**manifest, "written_at": datetime.now(UTC).isoformat()}
        self._append_table("manifests.models", row)
        data = json.dumps(row, indent=2, default=str).encode("utf-8")
        self.store.put_bytes(
            BUCKET_MANIFESTS, f"models/{mid}.json", data, content_type="application/json"
        )
        return row

    def write_telemetry(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        row = {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "payload": payload or {},
            "ts": datetime.now(UTC).isoformat(),
        }
        self._append_table("telemetry.events", row)

    def query_table(self, table: str, limit: int = 100) -> list[dict[str, Any]]:
        path = self.table_root / f"{table}.jsonl"
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        # errors=replace: binary/PDF noise must never crash the QA dashboard
        with path.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
                if len(rows) >= limit:
                    break
        return rows

    def list_manifests(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.query_table("manifests.datasets", limit=limit)

    def _append_table(self, table: str, record: dict[str, Any]) -> None:
        path = self.table_root / f"{table}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
