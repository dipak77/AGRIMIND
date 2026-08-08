"""Hybrid retrieval: stub + live Qdrant vector + Neo4j multi-hop graph (B1+B2)."""

from __future__ import annotations

import logging
import time
import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

try:
    from agrimind_kernel.contracts import Citation
except Exception:  # pragma: no cover
    Citation = None  # type: ignore

from memory.graph.neo4j_store import GraphPathHit, InMemoryGraphStore, Neo4jGraphStore
from memory.retrieval.semantic_cache import SemanticCache, compact_retrieval_payload
from memory.vector.embedder import LocalHashEmbedder
from memory.vector.qdrant_store import QdrantStore, VectorPoint
from memory.vector.seed_corpus import default_seed_documents

logger = logging.getLogger(__name__)


class RetrievalMode(StrEnum):
    GRAPH = "graph"
    VECTOR = "vector"
    HYBRID = "hybrid"
    API = "api"
    AUTO = "auto"


class ChunkWithCitation(BaseModel):
    chunk_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    text: str = ""
    content: str = ""
    score: float = 0.0
    citation: Any = None
    source_id: str = ""
    source_type: str = "document"
    url_or_path: str = ""
    checksum: str = ""
    lang: str = "en"
    metadata: dict = Field(default_factory=dict)

    def model_post_init(self, __context: object) -> None:
        if not self.text and self.content:
            self.text = self.content
        if not self.content and self.text:
            self.content = self.text


class GraphPathResult(BaseModel):
    path_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    nodes: list[dict] = Field(default_factory=list)
    relationships: list[dict] = Field(default_factory=list)
    confidence: float = 0.0
    is_approved: bool = True
    citations: list[dict] = Field(default_factory=list)
    summary: str = ""


class RetrievalTrace(BaseModel):
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    mode: RetrievalMode = RetrievalMode.HYBRID
    query: str = ""
    graph_results_count: int = 0
    vector_results_count: int = 0
    total_latency_ms: float = 0.0
    cache_hit: bool = False
    backend: str = "deterministic-stub"
    qdrant_url: str | None = None
    neo4j_uri: str | None = None
    embedder: str | None = None
    graph_backend: str | None = None
    error: str | None = None


class RetrievalRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    query: str
    lang: str = "en"
    mode: RetrievalMode | str = RetrievalMode.HYBRID
    top_k: int = 8
    filters: dict = Field(default_factory=dict)
    require_citations: bool = True


class RetrievalResult(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    query: str = ""
    chunks: list[ChunkWithCitation] = Field(default_factory=list)
    graph_paths: list[GraphPathResult] = Field(default_factory=list)
    confidence: float = 0.0
    trace: RetrievalTrace | None = None
    has_citations: bool = True


class RetrievalConfig(BaseModel):
    default_mode: RetrievalMode = RetrievalMode.HYBRID
    default_top_k: int = 8
    max_top_k: int = 50
    min_confidence_threshold: float = 0.5
    graph_enabled: bool = True
    vector_enabled: bool = True
    semantic_cache_enabled: bool = True
    semantic_cache_ttl_seconds: int = 3600
    semantic_cache_threshold: float = 0.92


class HybridRetriever:
    """
    backend:
      - stub: deterministic evidence (no network)
      - live: Qdrant + Neo4j when available
      - auto: try live, fall back to stub on failure
    """

    def __init__(
        self,
        backend: str = "stub",
        *,
        qdrant_url: str = "http://localhost:6333",
        qdrant_collection: str = "agrimind_chunks",
        qdrant_api_key: str | None = None,
        embed_dim: int = 384,
        store: QdrantStore | None = None,
        embedder: LocalHashEmbedder | None = None,
        graph_store: Any | None = None,
        neo4j_uri: str = "bolt://localhost:7687",
        neo4j_user: str = "neo4j",
        neo4j_password: str = "agrimind123",
        graph_enabled: bool = True,
        vector_enabled: bool = True,
        semantic_cache: SemanticCache | None = None,
        cache_enabled: bool = True,
        cache_ttl_seconds: int = 3600,
    ) -> None:
        self.backend = backend
        self.qdrant_url = qdrant_url
        self.qdrant_collection = qdrant_collection
        self.neo4j_uri = neo4j_uri
        self.graph_enabled = graph_enabled
        self.vector_enabled = vector_enabled
        self.semantic_cache = semantic_cache
        self.cache_enabled = bool(cache_enabled) and semantic_cache is not None
        self.cache_ttl_seconds = cache_ttl_seconds
        self.embedder = embedder or LocalHashEmbedder(dimension=embed_dim)
        self.store = store or QdrantStore(
            url=qdrant_url,
            collection=qdrant_collection,
            dimension=self.embedder.dimension,
            api_key=qdrant_api_key,
        )
        if graph_store is not None:
            self.graph = graph_store
            self._graph_backend = "injected"
        elif backend == "stub":
            self.graph = InMemoryGraphStore()
            self.graph.seed_default()
            self._graph_backend = "in_memory"
        else:
            # live/auto: prefer Neo4j, fall back to in-memory seeded graph
            try:
                ng = Neo4jGraphStore(uri=neo4j_uri, user=neo4j_user, password=neo4j_password)
                if ng.ping():
                    self.graph = ng
                    self._graph_backend = "neo4j"
                else:
                    self.graph = InMemoryGraphStore()
                    self.graph.seed_default()
                    self._graph_backend = "in_memory_fallback"
            except Exception:
                self.graph = InMemoryGraphStore()
                self.graph.seed_default()
                self._graph_backend = "in_memory_fallback"

    def retrieve(self, req: RetrievalRequest) -> RetrievalResult:
        mode = RetrievalMode(req.mode) if isinstance(req.mode, str) else req.mode
        start = time.time()

        if self.cache_enabled and self.semantic_cache is not None:
            try:
                cached = self.semantic_cache.get(req.query, req.lang)
            except Exception as exc:
                logger.warning("semantic_cache_get_failed: %s", exc)
                cached = None
            if cached is not None:
                return self._result_from_cache(req, mode, cached, start)

        if self.backend == "stub":
            result = self._retrieve_stub(req, mode, start)
        elif self.backend == "live":
            result = self._retrieve_live(req, mode, start)
        else:
            try:
                result = self._retrieve_live(req, mode, start)
            except Exception as exc:
                logger.warning("live_retrieve_failed_fallback_stub: %s", exc)
                result = self._retrieve_stub(req, mode, start)
                if result.trace:
                    result.trace.backend = "stub_fallback"
                    result.trace.error = str(exc)

        self._maybe_cache(req, result)
        return result

    def cache_stats(self) -> dict[str, Any]:
        if self.semantic_cache is None:
            return {
                "enabled": False,
                "backend": "none",
                "hits": 0,
                "misses": 0,
                "size": 0,
            }
        stats = self.semantic_cache.stats()
        stats["enabled"] = self.cache_enabled
        return stats

    def _maybe_cache(self, req: RetrievalRequest, result: RetrievalResult) -> None:
        if not self.cache_enabled or self.semantic_cache is None:
            return
        # Do not cache empty failures / hard errors
        if result.trace and result.trace.error:
            return
        if not result.chunks and not result.graph_paths:
            return
        try:
            payload = compact_retrieval_payload(result.model_dump(mode="json"))
            self.semantic_cache.set(
                req.query,
                req.lang,
                payload,
                ttl_seconds=self.cache_ttl_seconds,
            )
        except Exception as exc:
            logger.warning("semantic_cache_set_failed: %s", exc)

    def _result_from_cache(
        self,
        req: RetrievalRequest,
        mode: RetrievalMode,
        cached: dict[str, Any],
        start: float,
    ) -> RetrievalResult:
        chunks = [ChunkWithCitation.model_validate(c) for c in (cached.get("chunks") or [])]
        graph_paths = [
            GraphPathResult.model_validate(p) for p in (cached.get("graph_paths") or [])
        ]
        latency = (time.time() - start) * 1000
        return RetrievalResult(
            request_id=req.request_id,
            query=req.query,
            chunks=chunks[: req.top_k],
            graph_paths=graph_paths,
            confidence=float(cached.get("confidence") or 0.0),
            has_citations=bool(cached.get("has_citations", True)),
            trace=RetrievalTrace(
                mode=mode,
                query=req.query,
                graph_results_count=int(
                    cached.get("graph_results_count") or len(graph_paths)
                ),
                vector_results_count=int(cached.get("vector_results_count") or 0),
                total_latency_ms=latency,
                cache_hit=True,
                backend="cache",
                qdrant_url=cached.get("qdrant_url") or self.qdrant_url,
                neo4j_uri=cached.get("neo4j_uri") or self.neo4j_uri,
                embedder=cached.get("embedder") or self.embedder.model_id,
                graph_backend=cached.get("graph_backend") or self._graph_backend,
                error=None,
            ),
        )

    def seed_default_corpus(self) -> dict[str, Any]:
        docs = default_seed_documents()
        n = self.upsert_documents(docs)
        return {
            "upserted": n,
            "collection": self.qdrant_collection,
            "qdrant_url": self.qdrant_url,
            "embedder": self.embedder.model_id,
            "dimension": self.embedder.dimension,
        }

    def seed_default_graph(self) -> dict[str, Any]:
        result = self.graph.seed_default()
        result["graph_backend"] = self._graph_backend
        return result

    def upsert_documents(self, docs: list[dict[str, Any]]) -> int:
        points: list[VectorPoint] = []
        for d in docs:
            text = d.get("text") or d.get("content") or ""
            doc_id = d.get("doc_id") or d.get("source_id") or str(uuid.uuid4())
            vector = self.embedder.embed(text)
            payload = {
                "text": text,
                "title": d.get("title") or "",
                "source_id": d.get("source_id") or doc_id,
                "source_type": d.get("source_type") or "document",
                "url_or_path": d.get("url_or_path") or d.get("source_url") or "",
                "checksum": d.get("checksum") or "",
                "lang": d.get("lang") or "en",
                "span": d.get("span") or "",
                "excerpt": d.get("excerpt") or text[:500],
            }
            # Provenance for curated-ingest → retrieval (optional keys)
            for key in (
                "job_id",
                "document_id",
                "chunk_index",
                "source_url",
                "manifest_id",
                "license",
            ):
                if key in d and d[key] is not None:
                    payload[key] = d[key]
            points.append(VectorPoint(id=str(doc_id), vector=vector, payload=payload))
        return self.store.upsert(points)

    def health(self) -> dict[str, Any]:
        qdrant_ok = False
        points = 0
        if self.backend != "stub":
            try:
                qdrant_ok = self.store.ping()
                if qdrant_ok:
                    points = self.store.count()
            except Exception:
                qdrant_ok = False
        graph_ok = False
        graph_nodes = 0
        try:
            graph_ok = self.graph.ping()
            graph_nodes = self.graph.count_nodes()
        except Exception:
            graph_ok = False
        ok = True
        if self.backend == "live":
            ok = (qdrant_ok if self.vector_enabled else True) or (
                graph_ok if self.graph_enabled else True
            )
        return {
            "backend": self.backend,
            "qdrant": qdrant_ok,
            "points": points,
            "collection": self.qdrant_collection,
            "url": self.qdrant_url,
            "neo4j": graph_ok,
            "neo4j_uri": self.neo4j_uri,
            "graph_backend": self._graph_backend,
            "graph_nodes": graph_nodes,
            "ok": ok if self.backend != "stub" else True,
        }

    # --- internal ---

    def _graph_paths(self, query: str, top_k: int) -> list[GraphPathResult]:
        if not self.graph_enabled:
            return []
        try:
            hits: list[GraphPathHit] = self.graph.multi_hop_paths(query, top_k=top_k)
        except Exception as exc:
            logger.warning("graph_multi_hop_failed: %s", exc)
            return []
        paths: list[GraphPathResult] = []
        for h in hits:
            if not h.is_approved:
                continue
            paths.append(
                GraphPathResult(
                    path_id=h.path_id,
                    nodes=h.nodes,
                    relationships=h.relationships,
                    confidence=h.confidence,
                    is_approved=h.is_approved,
                    citations=h.citations,
                    summary=h.summary,
                )
            )
        return paths

    def _paths_to_chunks(self, paths: list[GraphPathResult], lang: str) -> list[ChunkWithCitation]:
        chunks: list[ChunkWithCitation] = []
        for p in paths:
            text = p.summary or "Graph path"
            if p.citations:
                text = f"{p.summary}. Provenance: {p.citations[0].get('source_id', '')}"
            citation = None
            src = (p.citations[0] if p.citations else {}) or {}
            if Citation is not None:
                citation = Citation(
                    source_id=str(src.get("source_id") or "kg"),
                    source_type="knowledge_graph",  # type: ignore[arg-type]
                    title=str(src.get("title") or "Knowledge graph path"),
                    url_or_path=str(src.get("url_or_path") or ""),
                    checksum=str(src.get("checksum") or ""),
                    span=str(src.get("span") or p.summary) or None,
                    excerpt=str(src.get("excerpt") or p.summary)[:800],
                    confidence=float(src.get("confidence") or p.confidence),
                )
            chunks.append(
                ChunkWithCitation(
                    text=text,
                    content=text,
                    score=float(p.confidence),
                    citation=citation,
                    source_id=str(src.get("source_id") or "kg"),
                    source_type="knowledge_graph",
                    url_or_path=str(src.get("url_or_path") or ""),
                    checksum=str(src.get("checksum") or ""),
                    lang=lang,
                    metadata={"backend": "graph", "path_id": p.path_id},
                )
            )
        return chunks

    def _vector_chunks(self, req: RetrievalRequest) -> list[ChunkWithCitation]:
        if not self.vector_enabled:
            return []
        qvec = self.embedder.embed(req.query)
        hits = self.store.search(qvec, top_k=req.top_k, filters=req.filters or None)
        chunks: list[ChunkWithCitation] = []
        for h in hits:
            p = h.payload
            citation = None
            if Citation is not None:
                citation = Citation(
                    source_id=str(p.get("source_id") or h.id),
                    source_type=p.get("source_type") or "document",  # type: ignore[arg-type]
                    title=str(p.get("title") or ""),
                    url_or_path=str(p.get("url_or_path") or ""),
                    checksum=str(p.get("checksum") or ""),
                    span=str(p.get("span") or "") or None,
                    excerpt=str(p.get("excerpt") or p.get("text") or "")[:800],
                    confidence=min(1.0, max(0.0, float(h.score))),
                )
            text = str(p.get("text") or p.get("excerpt") or "")
            chunks.append(
                ChunkWithCitation(
                    chunk_id=str(h.id),
                    text=text,
                    content=text,
                    score=float(h.score),
                    citation=citation,
                    source_id=str(p.get("source_id") or h.id),
                    source_type=str(p.get("source_type") or "document"),
                    url_or_path=str(p.get("url_or_path") or ""),
                    checksum=str(p.get("checksum") or ""),
                    lang=str(p.get("lang") or req.lang),
                    metadata={"backend": "vector", "score": h.score},
                )
            )
        return chunks

    def _retrieve_live(
        self,
        req: RetrievalRequest,
        mode: RetrievalMode,
        start: float,
    ) -> RetrievalResult:
        graph_paths: list[GraphPathResult] = []
        chunks: list[ChunkWithCitation] = []

        want_graph = mode in (
            RetrievalMode.GRAPH,
            RetrievalMode.HYBRID,
            RetrievalMode.AUTO,
        )
        want_vector = mode in (
            RetrievalMode.VECTOR,
            RetrievalMode.HYBRID,
            RetrievalMode.AUTO,
        )

        if want_graph:
            graph_paths = self._graph_paths(req.query, top_k=min(5, req.top_k))
            if mode == RetrievalMode.GRAPH:
                chunks = self._paths_to_chunks(graph_paths, req.lang)

        if want_vector and mode != RetrievalMode.GRAPH:
            try:
                chunks = self._vector_chunks(req)
            except Exception as exc:
                if mode == RetrievalMode.VECTOR:
                    raise
                logger.warning("vector_search_failed: %s", exc)
                chunks = []

        # hybrid: merge graph path chunks as additional evidence (dedupe by source_id)
        if mode in (RetrievalMode.HYBRID, RetrievalMode.AUTO) and graph_paths:
            seen = {c.source_id for c in chunks}
            for gc in self._paths_to_chunks(graph_paths, req.lang):
                if gc.source_id not in seen:
                    chunks.append(gc)
                    seen.add(gc.source_id)

        if not chunks and not graph_paths:
            raise RuntimeError(
                "Live retrieval returned no vector hits and no graph paths; "
                "seed Qdrant (/v1/index/seed) and/or graph (/v1/graph/seed)"
            )

        # confidence from best evidence
        scores = [c.score for c in chunks] + [p.confidence for p in graph_paths]
        top = max(scores) if scores else 0.5
        confidence = min(0.90, max(0.55, 0.5 + 0.45 * top))
        if req.require_citations and not any(c.citation for c in chunks) and not any(
            p.citations for p in graph_paths
        ):
            confidence = min(confidence, 0.6)

        latency = (time.time() - start) * 1000
        return RetrievalResult(
            request_id=req.request_id,
            query=req.query,
            chunks=chunks[: req.top_k],
            graph_paths=graph_paths,
            confidence=confidence,
            has_citations=any(c.citation for c in chunks)
            or any(bool(p.citations) for p in graph_paths),
            trace=RetrievalTrace(
                mode=mode,
                query=req.query,
                graph_results_count=len(graph_paths),
                vector_results_count=sum(
                    1 for c in chunks if (c.metadata or {}).get("backend") == "vector"
                ),
                total_latency_ms=latency,
                backend="live",
                qdrant_url=self.qdrant_url,
                neo4j_uri=self.neo4j_uri,
                embedder=self.embedder.model_id,
                graph_backend=self._graph_backend,
            ),
        )

    def _retrieve_stub(
        self,
        req: RetrievalRequest,
        mode: RetrievalMode,
        start: float,
    ) -> RetrievalResult:
        # Use in-memory graph for realistic multi-hop even in stub mode
        graph_paths = self._graph_paths(req.query, top_k=3)
        if not graph_paths:
            graph_paths = [
                GraphPathResult(
                    nodes=[
                        {"id": "crop:cotton", "type": "Crop", "name": "Cotton"},
                        {"id": "pest:bollworm", "type": "Pest", "name": "Bollworm"},
                        {"id": "practice:ipm", "type": "Practice", "name": "IPM"},
                    ],
                    relationships=[
                        {"relation": "AFFECTED_BY", "source": "crop:cotton", "target": "pest:bollworm"},
                        {"relation": "MANAGED_BY", "source": "pest:bollworm", "target": "practice:ipm"},
                    ],
                    confidence=0.78,
                    is_approved=True,
                    citations=[
                        {
                            "source_id": "src_icar_cotton_ipm_001",
                            "source_type": "knowledge_graph",
                            "url_or_path": "s3://agrimind-curated/icar/cotton-ipm.pdf",
                            "checksum": "sha256:seed-cotton-ipm",
                            "span": "Bollworm IPM",
                        }
                    ],
                    summary="Cotton -[AFFECTED_BY]-> Bollworm -[MANAGED_BY]-> IPM",
                )
            ]

        citation = None
        if Citation is not None:
            citation = Citation(
                source_id="src_icar_cotton_ipm_001",
                source_type="document",
                title="ICAR Cotton IPM Advisory",
                url_or_path="s3://agrimind-curated/icar/cotton-ipm.pdf",
                checksum="sha256:stub-index-not-production",
                span="Bollworm IPM",
                excerpt=(
                    "For cotton bollworm: use IPM — field monitoring, pheromone traps, "
                    "neem-based products, and approved chemicals only with agronomist guidance. "
                    "Banned chemicals must not be recommended."
                ),
                confidence=0.8,
            )
        text = citation.excerpt if citation else f"Evidence for: {req.query}"
        chunk = ChunkWithCitation(
            text=text,
            content=text,
            score=0.82,
            citation=citation,
            source_id="src_icar_cotton_ipm_001",
            source_type="document",
            url_or_path="s3://agrimind-curated/icar/cotton-ipm.pdf",
            checksum="sha256:stub-index-not-production",
            lang=req.lang,
            metadata={"backend": "stub", "mode": str(mode)},
        )
        # graph-mode: prefer graph chunks
        chunks = [chunk]
        if mode == RetrievalMode.GRAPH:
            chunks = self._paths_to_chunks(graph_paths, req.lang) or chunks

        confidence = 0.86 if req.require_citations else 0.7
        latency = (time.time() - start) * 1000
        return RetrievalResult(
            request_id=req.request_id,
            query=req.query,
            chunks=chunks,
            graph_paths=graph_paths,
            confidence=confidence,
            has_citations=True,
            trace=RetrievalTrace(
                mode=mode,
                query=req.query,
                graph_results_count=len(graph_paths),
                vector_results_count=1 if mode != RetrievalMode.GRAPH else 0,
                total_latency_ms=latency,
                backend="stub",
                embedder="none",
                graph_backend=self._graph_backend,
            ),
        )


RetrievalService = HybridRetriever
