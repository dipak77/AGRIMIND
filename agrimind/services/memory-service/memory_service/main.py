"""Memory service — hybrid retrieval (Qdrant vector + Neo4j graph)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agrimind_kernel.config.settings import get_settings
from memory.retrieval.semantic_cache import build_semantic_cache
from memory.retrieval.service import HybridRetriever, RetrievalRequest
from memory.vector.embedder import LocalHashEmbedder

logger = structlog.get_logger()
settings = get_settings()


def _build_retriever() -> HybridRetriever:
    backend = (settings.memory_backend or "auto").lower()
    embedder = LocalHashEmbedder(dimension=settings.embed_dim)
    cache = build_semantic_cache(
        settings.redis_url,
        enabled=settings.semantic_cache_enabled,
        threshold=settings.semantic_cache_threshold,
        ttl=settings.semantic_cache_ttl_seconds,
        embedder=embedder,
    )
    return HybridRetriever(
        backend=backend,
        qdrant_url=settings.qdrant_url,
        qdrant_collection=settings.qdrant_collection,
        qdrant_api_key=settings.qdrant_api_key,
        embed_dim=settings.embed_dim,
        embedder=embedder,
        neo4j_uri=settings.neo4j_uri,
        neo4j_user=settings.neo4j_user,
        neo4j_password=settings.neo4j_password,
        graph_enabled=True,
        vector_enabled=True,
        semantic_cache=cache,
        cache_enabled=settings.semantic_cache_enabled,
        cache_ttl_seconds=settings.semantic_cache_ttl_seconds,
    )


class SearchReq(BaseModel):
    query: str
    lang: str = "en"
    mode: str = "hybrid"
    top_k: int = Field(default=8, ge=1, le=50)


class UpsertDoc(BaseModel):
    doc_id: str | None = None
    text: str
    title: str = ""
    source_id: str | None = None
    source_type: str = "document"
    url_or_path: str = ""
    checksum: str = ""
    lang: str = "en"
    span: str = ""
    excerpt: str = ""


class UpsertReq(BaseModel):
    documents: list[UpsertDoc]


class GraphQueryReq(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=20)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.retriever = _build_retriever()
    logger.info(
        "memory-service starting",
        backend=app.state.retriever.backend,
        qdrant=settings.qdrant_url,
        neo4j=settings.neo4j_uri,
        graph_backend=app.state.retriever._graph_backend,
        semantic_cache=app.state.retriever.cache_stats(),
    )
    if app.state.retriever.backend in ("live", "auto"):
        # Vector auto-seed
        try:
            if app.state.retriever.store.ping():
                if app.state.retriever.store.count() == 0:
                    seeded = app.state.retriever.seed_default_corpus()
                    logger.info("qdrant_auto_seeded", **seeded)
        except Exception as exc:
            logger.warning("qdrant_auto_seed_skipped", error=str(exc))
        # Graph auto-seed when Neo4j empty
        try:
            if app.state.retriever.graph.ping() and app.state.retriever.graph.count_nodes() == 0:
                gseed = app.state.retriever.seed_default_graph()
                logger.info("graph_auto_seeded", **gseed)
        except Exception as exc:
            logger.warning("graph_auto_seed_skipped", error=str(exc))
    yield
    try:
        app.state.retriever.graph.close()
    except Exception:
        pass


app = FastAPI(title="memory-service", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health():
    retriever: HybridRetriever = app.state.retriever
    h = retriever.health()
    return {"status": "healthy", "service": "memory-service", **h}


@app.get("/ready")
async def ready():
    retriever: HybridRetriever = app.state.retriever
    h = retriever.health()
    if retriever.backend == "live" and not (h.get("qdrant") or h.get("neo4j")):
        raise HTTPException(
            status_code=503,
            detail="Neither Qdrant nor Neo4j reachable for live backend",
        )
    return {"status": "ready", **h}


@app.post("/v1/retrieve")
async def retrieve(req: SearchReq) -> dict[str, Any]:
    retriever: HybridRetriever = app.state.retriever
    r = RetrievalRequest(query=req.query, lang=req.lang, mode=req.mode, top_k=req.top_k)
    try:
        res = retriever.retrieve(r)
    except Exception as exc:
        logger.error("retrieve_failed", error=str(exc))
        raise HTTPException(status_code=503, detail=f"retrieve failed: {exc}") from exc
    return res.model_dump(mode="json")


@app.post("/v1/index/seed")
async def seed_index() -> dict[str, Any]:
    retriever: HybridRetriever = app.state.retriever
    try:
        result = retriever.seed_default_corpus()
        return {"status": "ok", **result}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"seed failed: {exc}") from exc


@app.post("/v1/index/upsert")
async def upsert_docs(req: UpsertReq) -> dict[str, Any]:
    retriever: HybridRetriever = app.state.retriever
    docs = [d.model_dump() for d in req.documents]
    try:
        n = retriever.upsert_documents(docs)
        return {"status": "ok", "upserted": n, "collection": settings.qdrant_collection}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"upsert failed: {exc}") from exc


@app.get("/v1/index/stats")
async def index_stats() -> dict[str, Any]:
    return app.state.retriever.health()


@app.get("/v1/cache/stats")
async def cache_stats() -> dict[str, Any]:
    """Semantic cache hits/misses/size/backend (B3)."""
    retriever: HybridRetriever = app.state.retriever
    return retriever.cache_stats()


@app.post("/v1/graph/seed")
async def seed_graph() -> dict[str, Any]:
    """Bootstrap Neo4j / in-memory graph with Crop–Pest–Practice seed."""
    retriever: HybridRetriever = app.state.retriever
    try:
        result = retriever.seed_default_graph()
        logger.info("graph_seed_complete", **result)
        return {"status": "ok", **result}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"graph seed failed: {exc}") from exc


@app.post("/v1/graph/query")
async def graph_query(req: GraphQueryReq) -> dict[str, Any]:
    """Multi-hop graph paths only (mode=graph)."""
    retriever: HybridRetriever = app.state.retriever
    r = RetrievalRequest(query=req.query, mode="graph", top_k=req.top_k)
    try:
        res = retriever.retrieve(r)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"graph query failed: {exc}") from exc
    return {
        "query": req.query,
        "paths": [p.model_dump(mode="json") for p in res.graph_paths],
        "chunks": [c.model_dump(mode="json") for c in res.chunks],
        "trace": res.trace.model_dump(mode="json") if res.trace else None,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8003)
