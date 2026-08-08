"""Data kernel pipeline package.

Heavy modules (ingest_pipeline) are imported lazily to avoid circular imports:
connectors → pipeline.download → pipeline package → ingest_pipeline → connectors.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "ChunkIndexer",
    "IngestPipeline",
    "IngestRequest",
    "IngestResult",
    "NoOpChunkIndexer",
    "RecordingChunkIndexer",
    "chunk_text",
    "title_from_url",
]


def __getattr__(name: str) -> Any:
    if name in ("chunk_text", "title_from_url"):
        from data_kernel.pipeline.chunking import chunk_text, title_from_url

        return {"chunk_text": chunk_text, "title_from_url": title_from_url}[name]
    if name in ("ChunkIndexer", "NoOpChunkIndexer", "RecordingChunkIndexer"):
        from data_kernel.pipeline.indexer import (
            ChunkIndexer,
            NoOpChunkIndexer,
            RecordingChunkIndexer,
        )

        return {
            "ChunkIndexer": ChunkIndexer,
            "NoOpChunkIndexer": NoOpChunkIndexer,
            "RecordingChunkIndexer": RecordingChunkIndexer,
        }[name]
    if name in ("IngestPipeline", "IngestRequest", "IngestResult"):
        from data_kernel.pipeline.ingest_pipeline import (
            IngestPipeline,
            IngestRequest,
            IngestResult,
        )

        return {
            "IngestPipeline": IngestPipeline,
            "IngestRequest": IngestRequest,
            "IngestResult": IngestResult,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
