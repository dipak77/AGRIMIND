"""Semantic retrieval cache (B3).

Exact + cosine-near query match. In-memory by default for tests;
Redis when reachable. Soft-imports redis so unit tests need no server.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from memory.vector.embedder import LocalHashEmbedder, cosine_similarity

logger = logging.getLogger(__name__)

try:
    import redis as redis_lib
except ImportError:  # pragma: no cover
    redis_lib = None  # type: ignore

_WS_RE = re.compile(r"\s+")


def normalize_query(query: str) -> str:
    return _WS_RE.sub(" ", (query or "").strip().lower())


def query_key_hash(query: str, lang: str) -> str:
    norm = f"{(lang or 'en').lower()}:{normalize_query(query)}"
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:24]


def compact_retrieval_payload(result_dict: dict[str, Any]) -> dict[str, Any]:
    """Shrink RetrievalResult-like dict for cache storage."""
    chunks_out: list[dict[str, Any]] = []
    for c in (result_dict.get("chunks") or [])[:8]:
        if not isinstance(c, dict):
            continue
        text = str(c.get("text") or c.get("content") or "")[:500]
        citation = c.get("citation")
        if citation is not None and hasattr(citation, "model_dump"):
            citation = citation.model_dump(mode="json")
        chunks_out.append(
            {
                "chunk_id": c.get("chunk_id") or "",
                "text": text,
                "content": str(c.get("content") or text)[:500],
                "score": float(c.get("score") or 0.0),
                "source_id": str(c.get("source_id") or ""),
                "source_type": str(c.get("source_type") or "document"),
                "url_or_path": str(c.get("url_or_path") or ""),
                "checksum": str(c.get("checksum") or ""),
                "lang": str(c.get("lang") or "en"),
                "metadata": dict(c.get("metadata") or {}),
                "citation": citation,
            }
        )

    paths_out: list[dict[str, Any]] = []
    for p in (result_dict.get("graph_paths") or [])[:5]:
        if not isinstance(p, dict):
            continue
        paths_out.append(
            {
                "path_id": p.get("path_id") or "",
                "summary": str(p.get("summary") or "")[:400],
                "confidence": float(p.get("confidence") or 0.0),
                "is_approved": bool(p.get("is_approved", True)),
                "nodes": list(p.get("nodes") or [])[:12],
                "relationships": list(p.get("relationships") or [])[:12],
                "citations": list(p.get("citations") or [])[:5],
            }
        )

    trace = result_dict.get("trace") or {}
    if hasattr(trace, "model_dump"):
        trace = trace.model_dump(mode="json")
    if not isinstance(trace, dict):
        trace = {}

    return {
        "query": str(result_dict.get("query") or ""),
        "confidence": float(result_dict.get("confidence") or 0.0),
        "has_citations": bool(result_dict.get("has_citations", True)),
        "chunks": chunks_out,
        "graph_paths": paths_out,
        "backend": str(trace.get("backend") or result_dict.get("backend") or "unknown"),
        "mode": str(trace.get("mode") or result_dict.get("mode") or "hybrid"),
        "graph_results_count": int(
            trace.get("graph_results_count")
            or result_dict.get("graph_results_count")
            or len(paths_out)
        ),
        "vector_results_count": int(
            trace.get("vector_results_count") or result_dict.get("vector_results_count") or 0
        ),
        "embedder": trace.get("embedder") or result_dict.get("embedder"),
        "graph_backend": trace.get("graph_backend") or result_dict.get("graph_backend"),
        "qdrant_url": trace.get("qdrant_url"),
        "neo4j_uri": trace.get("neo4j_uri"),
    }


@dataclass
class _CacheRecord:
    query_hash: str
    query_text: str
    lang: str
    embedding: list[float]
    payload: dict[str, Any]
    expires_at: float
    created_at: float = field(default_factory=time.time)


class SemanticCache(ABC):
    """Abstract semantic cache API used by HybridRetriever."""

    backend_name: str = "abstract"

    def __init__(
        self,
        *,
        threshold: float = 0.92,
        default_ttl: int = 3600,
        embedder: LocalHashEmbedder | None = None,
    ) -> None:
        self.threshold = threshold
        self.default_ttl = default_ttl
        self.embedder = embedder or LocalHashEmbedder(dimension=384)
        self.hits = 0
        self.misses = 0

    @abstractmethod
    def get(self, query: str, lang: str) -> dict[str, Any] | None:
        ...

    @abstractmethod
    def set(
        self,
        query: str,
        lang: str,
        result_dict: dict[str, Any],
        ttl_seconds: int | None = None,
    ) -> None:
        ...

    @abstractmethod
    def size(self) -> int:
        ...

    def stats(self) -> dict[str, Any]:
        return {
            "backend": self.backend_name,
            "hits": self.hits,
            "misses": self.misses,
            "size": self.size(),
            "threshold": self.threshold,
            "default_ttl": self.default_ttl,
        }

    def _embed(self, query: str) -> list[float]:
        return self.embedder.embed(normalize_query(query))

    def _is_expired(self, expires_at: float) -> bool:
        return time.time() > expires_at


class InMemorySemanticCache(SemanticCache):
    """Process-local cache for tests and Redis-unavailable environments."""

    backend_name = "memory"

    def __init__(
        self,
        *,
        threshold: float = 0.92,
        default_ttl: int = 3600,
        embedder: LocalHashEmbedder | None = None,
    ) -> None:
        super().__init__(threshold=threshold, default_ttl=default_ttl, embedder=embedder)
        # key: (lang, query_hash) -> record
        self._by_hash: dict[tuple[str, str], _CacheRecord] = {}
        # lang -> list of hashes for semantic scan
        self._by_lang: dict[str, list[str]] = {}

    def get(self, query: str, lang: str) -> dict[str, Any] | None:
        lang_key = (lang or "en").lower()
        qh = query_key_hash(query, lang_key)
        now = time.time()

        # exact
        rec = self._by_hash.get((lang_key, qh))
        if rec is not None:
            if rec.expires_at >= now:
                self.hits += 1
                return dict(rec.payload)
            self._evict(lang_key, qh)

        # semantic nearest
        qvec = self._embed(query)
        best: _CacheRecord | None = None
        best_score = -1.0
        for h in list(self._by_lang.get(lang_key, [])):
            r = self._by_hash.get((lang_key, h))
            if r is None:
                continue
            if r.expires_at < now:
                self._evict(lang_key, h)
                continue
            score = cosine_similarity(qvec, r.embedding)
            if score > best_score:
                best_score = score
                best = r

        if best is not None and best_score >= self.threshold:
            self.hits += 1
            return dict(best.payload)

        self.misses += 1
        return None

    def set(
        self,
        query: str,
        lang: str,
        result_dict: dict[str, Any],
        ttl_seconds: int | None = None,
    ) -> None:
        lang_key = (lang or "en").lower()
        qh = query_key_hash(query, lang_key)
        ttl = int(ttl_seconds if ttl_seconds is not None else self.default_ttl)
        now = time.time()
        rec = _CacheRecord(
            query_hash=qh,
            query_text=normalize_query(query),
            lang=lang_key,
            embedding=self._embed(query),
            payload=compact_retrieval_payload(result_dict),
            expires_at=now + max(1, ttl),
            created_at=now,
        )
        if (lang_key, qh) not in self._by_hash:
            self._by_lang.setdefault(lang_key, []).append(qh)
        self._by_hash[(lang_key, qh)] = rec

    def size(self) -> int:
        now = time.time()
        # lazy prune count
        n = 0
        for (lang_key, qh), rec in list(self._by_hash.items()):
            if rec.expires_at < now:
                self._evict(lang_key, qh)
            else:
                n += 1
        return n

    def _evict(self, lang_key: str, qh: str) -> None:
        self._by_hash.pop((lang_key, qh), None)
        lst = self._by_lang.get(lang_key)
        if lst and qh in lst:
            self._by_lang[lang_key] = [x for x in lst if x != qh]


class RedisSemanticCache(SemanticCache):
    """Redis-backed semantic cache. Keys: agrimind:sc:{lang}:{hash}."""

    backend_name = "redis"
    KEY_PREFIX = "agrimind:sc"
    INDEX_PREFIX = "agrimind:sc:idx"

    def __init__(
        self,
        client: Any,
        *,
        threshold: float = 0.92,
        default_ttl: int = 3600,
        embedder: LocalHashEmbedder | None = None,
    ) -> None:
        super().__init__(threshold=threshold, default_ttl=default_ttl, embedder=embedder)
        self._r = client

    def _entry_key(self, lang: str, qh: str) -> str:
        return f"{self.KEY_PREFIX}:{lang}:{qh}"

    def _index_key(self, lang: str) -> str:
        return f"{self.INDEX_PREFIX}:{lang}"

    def get(self, query: str, lang: str) -> dict[str, Any] | None:
        lang_key = (lang or "en").lower()
        qh = query_key_hash(query, lang_key)
        now = time.time()

        # exact
        raw = self._r.get(self._entry_key(lang_key, qh))
        if raw:
            try:
                data = json.loads(raw)
                if float(data.get("expires_at", 0)) >= now:
                    self.hits += 1
                    return dict(data["payload"])
            except Exception as exc:
                logger.warning("redis_cache_decode_failed: %s", exc)

        # semantic scan over index
        qvec = self._embed(query)
        best_payload: dict[str, Any] | None = None
        best_score = -1.0
        try:
            members = self._r.smembers(self._index_key(lang_key)) or set()
        except Exception as exc:
            logger.warning("redis_cache_index_failed: %s", exc)
            self.misses += 1
            return None

        for member in members:
            key = member.decode("utf-8") if isinstance(member, (bytes, bytearray)) else str(member)
            raw_m = self._r.get(key)
            if not raw_m:
                try:
                    self._r.srem(self._index_key(lang_key), key)
                except Exception:
                    pass
                continue
            try:
                data = json.loads(raw_m)
            except Exception:
                continue
            if float(data.get("expires_at", 0)) < now:
                continue
            emb = data.get("embedding") or []
            score = cosine_similarity(qvec, [float(x) for x in emb])
            if score > best_score:
                best_score = score
                best_payload = dict(data["payload"])

        if best_payload is not None and best_score >= self.threshold:
            self.hits += 1
            return best_payload

        self.misses += 1
        return None

    def set(
        self,
        query: str,
        lang: str,
        result_dict: dict[str, Any],
        ttl_seconds: int | None = None,
    ) -> None:
        lang_key = (lang or "en").lower()
        qh = query_key_hash(query, lang_key)
        ttl = int(ttl_seconds if ttl_seconds is not None else self.default_ttl)
        ttl = max(1, ttl)
        now = time.time()
        key = self._entry_key(lang_key, qh)
        body = {
            "query_hash": qh,
            "query_text": normalize_query(query),
            "lang": lang_key,
            "embedding": self._embed(query),
            "payload": compact_retrieval_payload(result_dict),
            "created_at": now,
            "expires_at": now + ttl,
        }
        try:
            self._r.setex(key, ttl, json.dumps(body))
            self._r.sadd(self._index_key(lang_key), key)
            # keep index key around; prune on get when keys expire
            self._r.expire(self._index_key(lang_key), max(ttl, self.default_ttl))
        except Exception as exc:
            logger.warning("redis_cache_set_failed: %s", exc)

    def size(self) -> int:
        total = 0
        try:
            # rough: sum sizes of known lang indexes via KEYS is costly;
            # use SCAN on entry prefix when available
            cursor = 0
            pattern = f"{self.KEY_PREFIX}:*"
            while True:
                cursor, keys = self._r.scan(cursor=cursor, match=pattern, count=200)
                # exclude index keys
                total += sum(
                    1
                    for k in keys
                    if not (
                        k.decode("utf-8") if isinstance(k, (bytes, bytearray)) else str(k)
                    ).startswith(self.INDEX_PREFIX)
                )
                if cursor == 0:
                    break
        except Exception:
            return total
        return total


def build_semantic_cache(
    redis_url: str | None = None,
    *,
    enabled: bool = True,
    threshold: float = 0.92,
    ttl: int = 3600,
    embedder: LocalHashEmbedder | None = None,
) -> SemanticCache | None:
    """
    Build a cache backend. Tries Redis ping when redis_url is set and redis is
    installed; falls back to in-memory. Returns None when disabled.
    """
    if not enabled:
        return None

    emb = embedder or LocalHashEmbedder(dimension=384)

    if redis_url and redis_lib is not None:
        try:
            client = redis_lib.from_url(redis_url, decode_responses=False, socket_connect_timeout=0.5)
            if client.ping():
                logger.info("semantic_cache_backend=redis url=%s", redis_url)
                return RedisSemanticCache(
                    client,
                    threshold=threshold,
                    default_ttl=ttl,
                    embedder=emb,
                )
        except Exception as exc:
            logger.info("semantic_cache_redis_unavailable_fallback_memory: %s", exc)

    logger.info("semantic_cache_backend=memory")
    return InMemorySemanticCache(threshold=threshold, default_ttl=ttl, embedder=emb)
