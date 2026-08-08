"""Chunk indexer protocol — inject memory/Qdrant without hard data_kernel→memory deps."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ChunkIndexer(Protocol):
    """
    Thin interface for post-curate vector indexing.

    Implementations live in the memory package (or tests) so data_kernel
    never imports qdrant-client / HybridRetriever.
    """

    def index_chunks(self, docs: list[dict[str, Any]]) -> int:
        """Upsert chunk documents. Returns number of points written."""
        ...


class NoOpChunkIndexer:
    """Default when indexing is disabled or backend unavailable."""

    backend: str = "noop"

    def index_chunks(self, docs: list[dict[str, Any]]) -> int:
        return 0


class RecordingChunkIndexer:
    """Test helper: records calls without a real vector store."""

    def __init__(self) -> None:
        self.calls: list[list[dict[str, Any]]] = []
        self.backend: str = "recording"

    def index_chunks(self, docs: list[dict[str, Any]]) -> int:
        self.calls.append(list(docs))
        return len(docs)

    @property
    def all_docs(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for batch in self.calls:
            out.extend(batch)
        return out
