"""Tokenizer Manager for loading and validating tokenizers."""
from typing import Optional, Dict
from pathlib import Path
import hashlib
from .schemas import TokenizerManifest


class TokenizerManager:
    """Manages tokenizer lifecycle with manifest validation."""
    
    def __init__(self, registry_path: str):
        self.registry_path = Path(registry_path)
        self._cache: Dict[str, TokenizerManifest] = {}
    
    def load_manifest(self, tokenizer_id: str) -> TokenizerManifest:
        """Load tokenizer manifest from registry."""
        if tokenizer_id in self._cache:
            return self._cache[tokenizer_id]
        
        manifest_path = self.registry_path / f"{tokenizer_id}.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Tokenizer manifest not found: {tokenizer_id}")
        
        import json
        with open(manifest_path) as f:
            data = json.load(f)
        
        manifest = TokenizerManifest(**data)
        self._cache[tokenizer_id] = manifest
        return manifest
    
    def verify_tokenizer(self, tokenizer_id: str, data: bytes) -> bool:
        """Verify tokenizer data against manifest checksum."""
        manifest = self.load_manifest(tokenizer_id)
        return manifest.verify_checksum(data)
    
    def register_tokenizer(self, manifest: TokenizerManifest, data: bytes) -> None:
        """Register a new tokenizer with checksum verification."""
        if not manifest.is_frozen:
            raise ValueError("Only frozen tokenizers can be registered")
        
        # Verify checksum matches
        computed = hashlib.sha256(data).hexdigest()
        if computed != manifest.checksum:
            raise ValueError(f"Checksum mismatch: expected {manifest.checksum}, got {computed}")
        
        # Save manifest
        manifest_path = self.registry_path / f"{manifest.tokenizer_id}.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        
        import json
        with open(manifest_path, 'w') as f:
            json.dump(manifest.model_dump(), f, indent=2, default=str)
