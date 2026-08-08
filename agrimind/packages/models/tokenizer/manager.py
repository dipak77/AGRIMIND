"""Tokenizer manager with fail-loud checksum + model linkage (D2)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict

from tokenizer.schemas import TokenizerManifest


class TokenizerManager:
    """Manages tokenizer lifecycle with manifest validation."""

    def __init__(self, registry_path: str | Path) -> None:
        self.registry_path = Path(registry_path)
        self.registry_path.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, TokenizerManifest] = {}

    def load_manifest(self, tokenizer_id: str) -> TokenizerManifest:
        if tokenizer_id in self._cache:
            return self._cache[tokenizer_id]
        manifest_path = self.registry_path / f"{tokenizer_id}.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Tokenizer manifest not found: {tokenizer_id}")
        with open(manifest_path, encoding="utf-8") as f:
            data = json.load(f)
        manifest = TokenizerManifest(**data)
        self._cache[tokenizer_id] = manifest
        return manifest

    def verify_tokenizer(self, tokenizer_id: str, data: bytes) -> bool:
        manifest = self.load_manifest(tokenizer_id)
        return manifest.verify_checksum(data)

    def assert_checksum(self, tokenizer_id: str, data: bytes) -> None:
        """Fail loud on checksum mismatch."""
        if not self.verify_tokenizer(tokenizer_id, data):
            manifest = self.load_manifest(tokenizer_id)
            computed = hashlib.sha256(data).hexdigest()
            raise ValueError(
                f"Tokenizer checksum mismatch for {tokenizer_id}: "
                f"expected {manifest.checksum}, got {computed}"
            )

    def register_tokenizer(self, manifest: TokenizerManifest, data: bytes) -> None:
        if not manifest.is_frozen:
            raise ValueError("Only frozen tokenizers can be registered")
        computed = hashlib.sha256(data).hexdigest()
        expected = manifest.checksum
        if expected.startswith("sha256:"):
            expected = expected.split(":", 1)[1]
        if computed != expected:
            raise ValueError(
                f"Checksum mismatch: expected {manifest.checksum}, got {computed}"
            )
        manifest_path = self.registry_path / f"{manifest.tokenizer_id}.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest.model_dump(mode="json"), f, indent=2, default=str)
        self._cache[manifest.tokenizer_id] = manifest

    def ensure_seed_default(self) -> str:
        """Seed default agrimind-tokenizer-v1 if missing."""
        tid = "agrimind-tokenizer-v1"
        path = self.registry_path / f"{tid}.json"
        if path.exists():
            return tid
        data = b"agrimind-tokenizer-v1-seed-bytes"
        checksum = hashlib.sha256(data).hexdigest()
        manifest = TokenizerManifest(
            tokenizer_id=tid,
            vocab_size=64000,
            model_family="agrimind",
            checksum=checksum,
            languages=["en", "hi", "mr"],
        )
        self.register_tokenizer(manifest, data)
        # also write blob for verify demos
        (self.registry_path / f"{tid}.blob").write_bytes(data)
        return tid
