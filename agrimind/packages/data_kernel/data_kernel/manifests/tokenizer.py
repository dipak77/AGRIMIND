"""Tokenizer manifest schemas for reproducible tokenization."""

from datetime import datetime

from pydantic import BaseModel, Field


class TokenizerManifest(BaseModel):
    """Immutable manifest for a tokenizer.

    Every model must reference a specific tokenizer manifest to ensure
    consistent tokenization across training and inference.
    """

    tokenizer_id: str = Field(..., description="Unique tokenizer identifier")
    version: str = Field(..., description="Semantic version of the tokenizer")

    # Model configuration
    vocab_size: int = Field(..., description="Vocabulary size")
    model_type: str = Field(..., description="Tokenizer type (e.g., BPE, WordPiece, Unigram)")
    model_family: str = Field(
        ..., description="Compatible model family (e.g., agrimind-18m, Qwen2.5)"
    )

    # Languages supported
    languages: list[str] = Field(..., description="Supported language codes (en, hi, mr)")

    # Normalization settings
    normalization: str = Field(
        ..., description="Normalization strategy (e.g., NFKC + transliteration)"
    )
    add_prefix_space: bool = Field(False, description="Whether to add prefix space")
    lowercase: bool = Field(False, description="Whether to lowercase input")

    # Special tokens
    bos_token: str | None = Field(None, description="Beginning of sequence token")
    eos_token: str | None = Field(None, description="End of sequence token")
    pad_token: str | None = Field(None, description="Padding token")
    unk_token: str | None = Field(None, description="Unknown token")
    cls_token: str | None = Field(None, description="Classification token")
    sep_token: str | None = Field(None, description="Separator token")
    mask_token: str | None = Field(None, description="Mask token")

    # Artifact location
    vocab_path: str = Field(..., description="Path to vocabulary file")
    merges_path: str | None = Field(None, description="Path to merges file (for BPE)")
    tokenizer_file_path: str = Field(..., description="Path to tokenizer.json file")
    artifact_checksum: str = Field(..., description="SHA-256 checksum of tokenizer artifacts")

    # Metadata
    description: str = Field("", description="Tokenizer description")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    frozen: bool = Field(False, description="If true, manifest cannot be modified")

    model_config = {"frozen": True}
