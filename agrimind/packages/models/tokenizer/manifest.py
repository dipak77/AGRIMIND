"""Immutable Tokenizer Manifest data structures and helpers (P0.1)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, List, Literal

from pydantic import BaseModel, Field


class TokenizerManifest(BaseModel):
    """Immutable Tokenizer Manifest."""
    tokenizer_id: str
    vocab_size: int
    model_family: str = "krishimini"
    checksum: str  # sha256 of vocabulary binary/json
    languages: List[Literal["en", "hi", "mr"]] = Field(default_factory=lambda: ["en", "hi", "mr"])
    normalization: str = "NFKC"
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    is_frozen: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    def verify_checksum(self, data: bytes) -> bool:
        """Verify binary data against stored SHA256 checksum."""
        expected = self.checksum
        if expected.startswith("sha256:"):
            expected = expected.split(":", 1)[1]
        computed = hashlib.sha256(data).hexdigest()
        return computed == expected

    def save(self, path: str | Path) -> None:
        """Persist manifest JSON to disk."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.model_dump(mode="json"), f, indent=2)

    @classmethod
    def load(cls, path: str | Path) -> TokenizerManifest:
        """Load manifest JSON from disk."""
        with open(path, encoding="utf-8") as f:
            return cls.model_validate(json.load(f))
