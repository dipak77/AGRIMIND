"""Dataset Manifest dataclass with provenance & checksum integrity (P0.7)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, List

from pydantic import BaseModel, Field


class DatasetManifest(BaseModel):
    """Immutable Dataset Product Manifest."""
    dataset_id: str
    version: int = 1
    dataset_product_type: str = "foundation_pretraining"  # foundation, rag, kg, sft, dpo, safety, eval
    source_policy_version: str = "v1.0"
    tokenizer_manifest_id: str = "krishimini-tokenizer-16k"
    split_policy: str = "group_level_anti_contamination"
    languages: List[str] = Field(default_factory=lambda: ["en", "hi", "mr"])
    token_count: int = 0
    document_count: int = 0
    shards_count: int = 0
    hash: str  # sha256 of all shard checksums
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    is_frozen: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.model_dump(mode="json"), f, indent=2)

    @classmethod
    def load(cls, path: str | Path) -> DatasetManifest:
        with open(path, encoding="utf-8") as f:
            return cls.model_validate(json.load(f))
