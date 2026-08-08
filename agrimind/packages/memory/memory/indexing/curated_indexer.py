"""Bridge: curated chunks → HybridRetriever / Qdrant (or in-memory fallback)."""

from __future__ import annotations

import logging
import os
from typing import Any

from memory.retrieval.service import HybridRetriever
from memory.vector.embedder import LocalHashEmbedder
from memory.vector.in_memory_store import InMemoryVectorStore
from memory.vector.qdrant_store import QdrantStore

logger = logging.getLogger(__name__)


class MemoryChunkIndexer:
    """
    Implements data_kernel.pipeline.indexer.ChunkIndexer using HybridRetriever.

    Works with live QdrantStore or injectable/in-memory store (tests/offline).
    """

    def __init__(
        self,
        retriever: HybridRetriever | None = None,
        *,
        store: Any | None = None,
        embedder: LocalHashEmbedder | None = None,
        qdrant_url: str = "http://localhost:6333",
        collection: str = "agrimind_chunks",
        embed_dim: int = 384,
        backend_label: str | None = None,
    ) -> None:
        self.embedder = embedder or LocalHashEmbedder(dimension=embed_dim)
        if retriever is not None:
            self.retriever = retriever
            self._backend = backend_label or getattr(retriever, "backend", "injected")
            if store is not None:
                self.store = store
            else:
                self.store = getattr(retriever, "store", None)
        else:
            self.store = store or InMemoryVectorStore(
                collection=collection,
                dimension=self.embedder.dimension,
            )
            self.retriever = HybridRetriever(
                backend="live",
                store=self.store,  # type: ignore[arg-type]
                embedder=self.embedder,
                qdrant_url=qdrant_url,
                qdrant_collection=collection,
                vector_enabled=True,
                graph_enabled=False,
                cache_enabled=False,
            )
            self._backend = backend_label or _store_backend_label(self.store)

    @property
    def backend(self) -> str:
        return self._backend

    def index_chunks(self, docs: list[dict[str, Any]]) -> int:
        if not docs:
            return 0
        prepared = [_prepare_doc(d) for d in docs]
        n = self.retriever.upsert_documents(prepared)
        logger.info(
            "curated_chunks_indexed",
            extra={"upserted": n, "backend": self._backend},
        )
        return n


def _prepare_doc(d: dict[str, Any]) -> dict[str, Any]:
    """Normalize chunk dict for HybridRetriever.upsert_documents."""
    text = d.get("text") or d.get("content") or ""
    chunk_index = d.get("chunk_index", 0)
    document_id = d.get("document_id") or d.get("source_id") or ""
    job_id = d.get("job_id") or ""
    doc_id = d.get("doc_id") or d.get("id")
    if not doc_id:
        base = document_id or d.get("source_id") or "doc"
        doc_id = f"{base}:chunk:{chunk_index}"

    out = {
        "doc_id": str(doc_id),
        "text": text,
        "title": d.get("title") or "",
        "source_id": str(d.get("source_id") or document_id or doc_id),
        "source_type": d.get("source_type") or "document",
        "url_or_path": d.get("url_or_path") or d.get("source_url") or "",
        "checksum": d.get("checksum") or "",
        "lang": d.get("lang") or "en",
        "span": d.get("span") or f"chunk:{chunk_index}",
        "excerpt": d.get("excerpt") or text[:500],
        # provenance retained in payload via upsert (extra keys ignored by default
        # HybridRetriever payload builder — re-add below if needed)
        "document_id": document_id,
        "job_id": job_id,
        "chunk_index": chunk_index,
        "source_url": d.get("source_url") or d.get("url_or_path") or "",
    }
    return out


def _store_backend_label(store: Any) -> str:
    if store is None:
        return "none"
    if isinstance(store, InMemoryVectorStore):
        return "in_memory"
    if isinstance(store, QdrantStore):
        return "qdrant"
    name = type(store).__name__
    if "Fake" in name or "InMemory" in name:
        return "in_memory"
    return name.lower()


def build_default_indexer(
    qdrant_url: str | None = None,
    collection: str | None = None,
    *,
    embed_dim: int | None = None,
    api_key: str | None = None,
    prefer_in_memory: bool = False,
    store: Any | None = None,
    embedder: LocalHashEmbedder | None = None,
) -> MemoryChunkIndexer:
    """
    Build a MemoryChunkIndexer.

    - If ``store`` is injected, use it (tests).
    - If ``prefer_in_memory`` or live Qdrant unreachable, use InMemoryVectorStore.
    - Env: QDRANT_URL, QDRANT_COLLECTION, QDRANT_API_KEY, EMBED_DIM
    """
    url = (qdrant_url or os.getenv("QDRANT_URL") or "http://localhost:6333").rstrip("/")
    coll = collection or os.getenv("QDRANT_COLLECTION") or "agrimind_chunks"
    dim = int(embed_dim or os.getenv("EMBED_DIM") or 384)
    key = api_key if api_key is not None else os.getenv("QDRANT_API_KEY")
    emb = embedder or LocalHashEmbedder(dimension=dim)

    if store is not None:
        return MemoryChunkIndexer(
            store=store,
            embedder=emb,
            qdrant_url=url,
            collection=coll,
            embed_dim=dim,
            backend_label=_store_backend_label(store),
        )

    if prefer_in_memory:
        mem = InMemoryVectorStore(collection=coll, dimension=dim)
        return MemoryChunkIndexer(
            store=mem,
            embedder=emb,
            qdrant_url=url,
            collection=coll,
            embed_dim=dim,
            backend_label="in_memory",
        )

    # Try live Qdrant
    try:
        qstore = QdrantStore(url=url, collection=coll, dimension=dim, api_key=key)
        if qstore.ping():
            qstore.ensure_collection()
            return MemoryChunkIndexer(
                store=qstore,
                embedder=emb,
                qdrant_url=url,
                collection=coll,
                embed_dim=dim,
                backend_label="qdrant",
            )
        logger.warning("qdrant_unreachable_using_in_memory", extra={"url": url})
    except Exception as exc:
        logger.warning("qdrant_init_failed_using_in_memory: %s", exc)

    mem = InMemoryVectorStore(collection=coll, dimension=dim)
    return MemoryChunkIndexer(
        store=mem,
        embedder=emb,
        qdrant_url=url,
        collection=coll,
        embed_dim=dim,
        backend_label="in_memory",
    )
