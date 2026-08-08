"""Object storage for raw/curated/quarantine artifacts.

MinIO when reachable; otherwise local filesystem lakehouse (labeled honestly).
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# How often to re-probe MinIO after a failed auto-detect (seconds).
# Avoids reconnect spam when the QA dashboard polls every few seconds.
_MINIO_PROBE_COOLDOWN_S = 60.0
# Short connect timeout so a down MinIO fails fast instead of multi-retry hangs.
_MINIO_CONNECT_TIMEOUT_S = 1.0
_MINIO_READ_TIMEOUT_S = 2.0

_cache_lock = threading.Lock()
# cache_key -> (resolved store, minio_ok | None, mono_time of resolution)
_store_cache: dict[tuple, tuple[ObjectStore, bool | None, float]] = {}
_last_ping_log_at: float = 0.0
_PING_LOG_COOLDOWN_S = 60.0


@dataclass
class PutResult:
    bucket: str
    key: str
    checksum: str
    size_bytes: int
    backend: str
    uri: str


class ObjectStore(Protocol):
    def put_bytes(self, bucket: str, key: str, data: bytes, content_type: str = "application/octet-stream") -> PutResult: ...
    def get_bytes(self, bucket: str, key: str) -> bytes: ...
    def exists(self, bucket: str, key: str) -> bool: ...
    def list_keys(self, bucket: str, prefix: str = "") -> list[str]: ...
    def ping(self) -> bool: ...
    @property
    def backend(self) -> str: ...


class LocalObjectStore:
    """Filesystem-backed object store under root/bucket/key."""

    def __init__(self, root: str | Path = "./data/lakehouse") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @property
    def backend(self) -> str:
        return "local_fs"

    def ping(self) -> bool:
        return self.root.exists()

    def _path(self, bucket: str, key: str) -> Path:
        p = self.root / bucket / key
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def put_bytes(
        self,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> PutResult:
        path = self._path(bucket, key)
        checksum = "sha256:" + hashlib.sha256(data).hexdigest()
        # Immutable: never overwrite an existing object key
        if path.exists():
            existing = path.read_bytes()
            existing_cs = "sha256:" + hashlib.sha256(existing).hexdigest()
            if existing_cs != checksum:
                raise FileExistsError(
                    f"immutable object already exists: {bucket}/{key} "
                    f"(existing={existing_cs}, new={checksum})"
                )
            return PutResult(
                bucket=bucket,
                key=key,
                checksum=existing_cs,
                size_bytes=len(existing),
                backend=self.backend,
                uri=f"file://{path.resolve()}",
            )
        path.write_bytes(data)
        # sidecar metadata for provenance
        meta = {
            "content_type": content_type,
            "checksum": checksum,
            "size_bytes": len(data),
            "immutable": True,
        }
        path.with_suffix(path.suffix + ".meta.json").write_text(
            json.dumps(meta), encoding="utf-8"
        )
        return PutResult(
            bucket=bucket,
            key=key,
            checksum=checksum,
            size_bytes=len(data),
            backend=self.backend,
            uri=f"file://{path.resolve()}",
        )

    def get_bytes(self, bucket: str, key: str) -> bytes:
        return self._path(bucket, key).read_bytes()

    def exists(self, bucket: str, key: str) -> bool:
        return self._path(bucket, key).exists()

    def list_keys(self, bucket: str, prefix: str = "") -> list[str]:
        base = self.root / bucket
        if not base.exists():
            return []
        keys: list[str] = []
        for p in base.rglob("*"):
            if p.is_file() and not p.name.endswith(".meta.json"):
                rel = str(p.relative_to(base)).replace("\\", "/")
                if rel.startswith(prefix):
                    keys.append(rel)
        return sorted(keys)


def _log_minio_ping_failed(exc: BaseException) -> None:
    """Rate-limit connection-refused noise (dashboard polls every few seconds)."""
    global _last_ping_log_at
    now = time.monotonic()
    if now - _last_ping_log_at < _PING_LOG_COOLDOWN_S:
        logger.debug("minio_ping_failed: %s", exc)
        return
    _last_ping_log_at = now
    logger.warning(
        "minio_ping_failed (using local_fs until next probe in %.0fs): %s",
        _MINIO_PROBE_COOLDOWN_S,
        exc,
    )


class MinioObjectStore:
    """MinIO/S3 via minio SDK when installed and reachable."""

    def __init__(
        self,
        endpoint: str = "http://localhost:9000",
        access_key: str = "minioadmin",
        secret_key: str = "minioadmin",
        secure: bool | None = None,
    ) -> None:
        parsed = urlparse(endpoint if "://" in endpoint else f"http://{endpoint}")
        self.endpoint = parsed.netloc or parsed.path
        self.access_key = access_key
        self.secret_key = secret_key
        self.secure = secure if secure is not None else (parsed.scheme == "https")
        self._client = None

    @property
    def backend(self) -> str:
        return "minio"

    def _http_client(self):
        """urllib3 pool with short timeouts so unreachable MinIO fails fast."""
        import urllib3

        timeout = urllib3.Timeout(
            connect=_MINIO_CONNECT_TIMEOUT_S,
            read=_MINIO_READ_TIMEOUT_S,
        )
        return urllib3.PoolManager(
            timeout=timeout,
            retries=False,
            maxsize=4,
        )

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from minio import Minio
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("minio package not installed") from exc
        self._client = Minio(
            self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=self.secure,
            http_client=self._http_client(),
        )
        return self._client

    def ping(self) -> bool:
        try:
            client = self._get_client()
            client.list_buckets()
            return True
        except Exception as exc:
            _log_minio_ping_failed(exc)
            return False

    def _ensure_bucket(self, bucket: str) -> None:
        client = self._get_client()
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)

    def put_bytes(
        self,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> PutResult:
        from io import BytesIO

        self._ensure_bucket(bucket)
        client = self._get_client()
        client.put_object(
            bucket,
            key,
            BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        checksum = "sha256:" + hashlib.sha256(data).hexdigest()
        return PutResult(
            bucket=bucket,
            key=key,
            checksum=checksum,
            size_bytes=len(data),
            backend=self.backend,
            uri=f"s3://{bucket}/{key}",
        )

    def get_bytes(self, bucket: str, key: str) -> bytes:
        client = self._get_client()
        resp = client.get_object(bucket, key)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()

    def exists(self, bucket: str, key: str) -> bool:
        try:
            self._get_client().stat_object(bucket, key)
            return True
        except Exception:
            return False

    def list_keys(self, bucket: str, prefix: str = "") -> list[str]:
        client = self._get_client()
        if not client.bucket_exists(bucket):
            return []
        return sorted(
            o.object_name
            for o in client.list_objects(bucket, prefix=prefix, recursive=True)
            if o.object_name
        )


def clear_object_store_cache() -> None:
    """Drop cached auto-detect results (tests / after MinIO comes online)."""
    global _last_ping_log_at
    with _cache_lock:
        _store_cache.clear()
        _last_ping_log_at = 0.0


def build_object_store(
    *,
    minio_endpoint: str = "http://localhost:9000",
    minio_access_key: str = "minioadmin",
    minio_secret_key: str = "minioadmin",
    local_root: str = "./data/lakehouse",
    prefer: str = "auto",
    use_cache: bool = True,
) -> ObjectStore:
    """prefer: auto | minio | local

    In ``auto`` mode, MinIO is probed once; on failure we fall back to local_fs
    and skip re-probing for ``_MINIO_PROBE_COOLDOWN_S`` so frequent callers
    (QA dashboard poll) do not spam connection errors.
    """
    prefer = (prefer or "auto").strip().lower()
    if prefer == "local":
        return LocalObjectStore(local_root)

    cache_key = (
        prefer,
        minio_endpoint,
        minio_access_key,
        minio_secret_key,
        str(Path(local_root).resolve()) if local_root else local_root,
    )
    now = time.monotonic()

    if use_cache:
        with _cache_lock:
            hit = _store_cache.get(cache_key)
            if hit is not None:
                store, minio_ok, resolved_at = hit
                # Keep a live MinIO store indefinitely until process restart.
                if minio_ok is True:
                    return store
                # After a failed probe, reuse local fallback until cooldown ends.
                if minio_ok is False and (now - resolved_at) < _MINIO_PROBE_COOLDOWN_S:
                    return store

    if prefer in ("auto", "minio"):
        try:
            store = MinioObjectStore(
                endpoint=minio_endpoint,
                access_key=minio_access_key,
                secret_key=minio_secret_key,
            )
            if store.ping():
                if use_cache:
                    with _cache_lock:
                        _store_cache[cache_key] = (store, True, time.monotonic())
                return store
        except Exception as exc:
            logger.info("minio_unavailable_using_local: %s", exc)
            if prefer == "minio":
                raise

        if prefer == "minio":
            raise RuntimeError(
                f"MinIO not reachable at {minio_endpoint}; "
                "start MinIO or set OBJECT_STORE=local"
            )

    local = LocalObjectStore(local_root)
    if use_cache and prefer == "auto":
        with _cache_lock:
            _store_cache[cache_key] = (local, False, time.monotonic())
        logger.info(
            "object_store_backend=local_fs (MinIO unavailable at %s; "
            "re-probe in %.0fs or set OBJECT_STORE=local)",
            minio_endpoint,
            _MINIO_PROBE_COOLDOWN_S,
        )
    return local
