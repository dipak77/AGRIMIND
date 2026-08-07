"""Dataset manifest schemas for immutable data versioning."""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field, HttpUrl


def _dataset_id_factory() -> str:
    """Generate dataset ID with current date."""
    return f"ds-{datetime.now(UTC).strftime('%Y%m%d')}-{uuid4().hex[:8]}"


class LicenseType(StrEnum):
    """Supported license types for agricultural data."""

    CC0 = "CC0-1.0"
    CC_BY = "CC-BY-4.0"
    CC_BY_SA = "CC-BY-SA-4.0"
    CC_BY_NC = "CC-BY-NC-4.0"
    CC_BY_ND = "CC-BY-ND-4.0"
    CC_BY_NC_SA = "CC-BY-NC-SA-4.0"
    CC_BY_NC_ND = "CC-BY-NC-ND-4.0"
    ODC_BY = "ODC-By-1.0"
    ODC_ODBL = "ODbL-1.0"
    GOVERNMENT_OPEN = "Government-Open"
    PROPRIETARY = "Proprietary"
    UNKNOWN = "Unknown"


class SourceMetadata(BaseModel):
    """Metadata about the source of ingested data."""

    source_id: str = Field(..., description="Unique identifier for the source")
    source_type: str = Field(
        ..., description="Type of source: web, pdf, rss, json, image, audio, structured"
    )
    url: HttpUrl | None = Field(None, description="Original URL if applicable")
    path: str | None = Field(None, description="File path in object storage")
    checksum: str = Field(..., description="SHA-256 checksum of the raw data")
    license: LicenseType = Field(..., description="License type of the source")
    fetched_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="When the data was fetched"
    )
    robots_txt_compliant: bool = Field(True, description="Whether robots.txt was respected")
    language: str | None = Field(None, description="Detected language code (en/hi/mr)")
    size_bytes: int = Field(..., description="Size of the raw data in bytes")
    metadata_extra: dict[str, object] = Field(
        default_factory=dict, description="Additional source-specific metadata"
    )


class DatasetManifest(BaseModel):
    """Immutable manifest for a versioned dataset.

    Every dataset must have a unique manifest ID that is referenced by models
    trained on this dataset. This ensures reproducibility.
    """

    manifest_id: str = Field(
        default_factory=_dataset_id_factory,
        description="Unique manifest identifier",
    )
    name: str = Field(..., description="Human-readable dataset name")
    version: str = Field(..., description="Semantic version of the dataset")
    description: str = Field(..., description="Description of the dataset contents")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Creation timestamp"
    )
    sources: list[SourceMetadata] = Field(
        ..., description="List of source metadata for all ingested data"
    )
    total_records: int = Field(..., description="Total number of records in the dataset")
    total_size_bytes: int = Field(..., description="Total size of the dataset in bytes")
    languages: list[str] = Field(
        default_factory=list, description="Languages present in the dataset"
    )
    modalities: list[str] = Field(
        default_factory=list, description="Modalities: text, image, audio, structured"
    )
    quality_score: float = Field(..., ge=0.0, le=1.0, description="Overall quality score (0-1)")
    pii_redacted: bool = Field(False, description="Whether PII has been redacted from the dataset")
    deduplicated: bool = Field(False, description="Whether duplicates have been removed")
    agriculture_relevance_score: float = Field(
        ..., ge=0.0, le=1.0, description="Relevance to agriculture domain (0-1)"
    )
    schema_version: str = Field("1.0.0", description="Schema version for the dataset structure")
    lakehouse_path: str = Field(
        ..., description="Path to the dataset in the lakehouse (Iceberg/Parquet)"
    )
    checksum: str = Field("", description="SHA-256 checksum of the manifest itself")
    frozen: bool = Field(False, description="If true, this manifest cannot be modified")
    parent_manifest_id: str | None = Field(
        None, description="Parent manifest ID if this is an incremental update"
    )
    tags: list[str] = Field(default_factory=list, description="Dataset tags for filtering")

    model_config = {"frozen": True}  # Immutable after creation

    def compute_checksum(self) -> str:
        """Compute SHA-256 checksum of the manifest content."""
        import hashlib

        content = self.model_dump_json(exclude={"checksum", "frozen"})
        return hashlib.sha256(content.encode()).hexdigest()

    def freeze(self) -> "DatasetManifest":
        """Freeze the manifest and compute its checksum."""
        checksum = self.compute_checksum()
        return self.model_copy(update={"checksum": checksum, "frozen": True})
