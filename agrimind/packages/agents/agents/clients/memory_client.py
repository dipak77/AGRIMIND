"""Memory-service HTTP client with optional local HybridRetriever fallback."""

from __future__ import annotations

from typing import Any

import httpx

from agrimind_kernel.contracts import Citation

try:
    from memory.retrieval.service import HybridRetriever, RetrievalRequest
except Exception:  # pragma: no cover
    HybridRetriever = None  # type: ignore
    RetrievalRequest = None  # type: ignore


class MemoryClient:
    """
    Prefer memory-service over HTTP.
    Fall back to in-process HybridRetriever only when allow_local_fallback=True
    (local/dev/tests). Production should fail closed or degrade confidence.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8003",
        *,
        timeout: float = 3.0,
        allow_local_fallback: bool = True,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.allow_local_fallback = allow_local_fallback
        self._client = client

    async def retrieve(
        self,
        query: str,
        lang: str = "en",
        mode: str = "hybrid",
        top_k: int = 5,
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        payload = {"query": query, "lang": lang, "mode": mode, "top_k": top_k}
        hdrs = headers or {}
        try:
            if self._client is not None:
                resp = await self._client.post(
                    f"{self.base_url}/v1/retrieve",
                    json=payload,
                    headers=hdrs,
                    timeout=self.timeout,
                )
            else:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(
                        f"{self.base_url}/v1/retrieve",
                        json=payload,
                        headers=hdrs,
                    )
            resp.raise_for_status()
            data = resp.json()
            data["_backend"] = "http"
            data["_memory_url"] = self.base_url
            return data
        except Exception as exc:
            if not self.allow_local_fallback:
                raise RuntimeError(f"memory-service unreachable: {exc}") from exc
            local = self.retrieve_local(query, lang=lang, mode=mode, top_k=top_k)
            local["_backend"] = "local_fallback"
            local["_fallback_reason"] = str(exc)
            return local

    def retrieve_local(
        self,
        query: str,
        lang: str = "en",
        mode: str = "hybrid",
        top_k: int = 5,
    ) -> dict[str, Any]:
        if HybridRetriever is None or RetrievalRequest is None:
            citation = Citation(
                source_id="src_local_emergency",
                source_type="document",
                title="Local emergency stub",
                url_or_path="local://stub",
                checksum="sha256:local",
                excerpt="Prefer IPM; consult KVK. No live index available.",
                confidence=0.7,
            )
            return {
                "query": query,
                "chunks": [
                    {
                        "text": citation.excerpt,
                        "score": 0.7,
                        "citation": citation.model_dump(mode="json"),
                        "source_id": citation.source_id,
                    }
                ],
                "graph_paths": [],
                "confidence": 0.7,
                "has_citations": True,
            }
        retriever = HybridRetriever(backend="stub")
        res = retriever.retrieve(
            RetrievalRequest(query=query, lang=lang, mode=mode, top_k=top_k)
        )
        return res.model_dump(mode="json")

    @staticmethod
    def parse_citations(result: dict[str, Any]) -> list[Citation]:
        citations: list[Citation] = []
        for chunk in result.get("chunks") or []:
            raw = chunk.get("citation")
            if raw:
                try:
                    citations.append(Citation.model_validate(raw))
                    continue
                except Exception:
                    pass
            # reconstruct from chunk fields
            citations.append(
                Citation(
                    source_id=chunk.get("source_id") or "unknown",
                    source_type=chunk.get("source_type") or "document",
                    title=chunk.get("title") or "",
                    url_or_path=chunk.get("url_or_path") or "",
                    checksum=chunk.get("checksum") or "",
                    excerpt=chunk.get("text") or chunk.get("content") or "",
                    confidence=float(chunk.get("score") or 0.7),
                )
            )
        return [c for c in citations if c.source_id]
