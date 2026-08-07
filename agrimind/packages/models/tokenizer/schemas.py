"""Tokenizer schemas and manifests."""
from pydantic import BaseModel, Field
from typing import List, Literal, Optional
from datetime import datetime
import hashlib


class TokenizerManifest(BaseModel):
    """Immutable tokenizer manifest with provenance."""
    tokenizer_id: str
    vocab_size: int
    model_family: str
    checksum: str  # sha256 of tokenizer file
    languages: List[Literal["en", "hi", "mr"]]
    normalization: str = "NFKC"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_frozen: bool = True
    
    class Config:
        frozen = True
    
    def verify_checksum(self, data: bytes) -> bool:
        """Verify tokenizer data against stored checksum."""
        computed = hashlib.sha256(data).hexdigest()
        return computed == self.checksum
