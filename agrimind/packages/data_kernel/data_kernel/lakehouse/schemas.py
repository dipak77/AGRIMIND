"""Lakehouse schemas for raw, curated, and quarantine data."""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class DocumentStatus(Enum):
    """Status of a document in the pipeline."""

    RAW = "raw"
    CURATED = "curated"
    QUARANTINE = "quarantine"
    DELETED = "deleted"


class SourceType(Enum):
    """Type of data source."""

    WEB = "web"
    PDF = "pdf"
    JSON = "json"
    RSS = "rss"
    WIKIPEDIA = "wikipedia"
    IMAGE = "image"
    AUDIO = "audio"
    STRUCTURED = "structured"


class RawDocument(BaseModel):
    """Raw document as ingested from source."""

    document_id: UUID = Field(default_factory=uuid4)
    source_id: str
    source_type: SourceType
    raw_content: bytes
    content_hash: str
    source_url: str | None = None
    ingested_at: datetime = Field(default_factory=datetime.utcnow)
    license_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    size_bytes: int

    class Config:
        arbitrary_types_allowed = True


class CuratedDocument(BaseModel):
    """Curated document after processing and filtering."""

    document_id: UUID
    source_id: str
    source_type: SourceType
    content: str
    language: str
    content_hash: str
    source_url: str | None = None
    curated_at: datetime = Field(default_factory=datetime.utcnow)
    license_type: str
    agriculture_relevance_score: float = Field(ge=0.0, le=1.0)
    quality_score: float = Field(ge=0.0, le=1.0)
    pii_redacted: bool = False
    toxicity_filtered: bool = False
    duplicate_of: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)

    class Config:
        arbitrary_types_allowed = True


class DocumentChunk(BaseModel):
    """Chunk of a curated document for retrieval."""

    chunk_id: UUID = Field(default_factory=uuid4)
    document_id: UUID
    chunk_index: int
    content: str
    embedding_model: str
    embedding_vector: list[float] | None = None
    start_offset: int
    end_offset: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class QuarantineReason(Enum):
    """Reason for quarantining a record."""

    LICENSE_INVALID = "license_invalid"
    SOURCE_NOT_ALLOWED = "source_not_allowed"
    PII_DETECTED = "pii_detected"
    TOXICITY_HIGH = "toxicity_high"
    RELEVANCE_LOW = "relevance_low"
    QUALITY_LOW = "quality_low"
    DUPLICATE_SUSPECTED = "duplicate_suspected"
    CHECKSUM_MISMATCH = "checksum_mismatch"
    SCHEMA_VALIDATION_FAILED = "schema_validation_failed"
    ROBOTS_TXT_VIOLATION = "robots_txt_violation"


class QuarantineRecord(BaseModel):
    """Record in quarantine requiring review."""

    record_id: UUID = Field(default_factory=uuid4)
    original_document_id: UUID | None = None
    source_id: str
    source_type: SourceType
    raw_content_hash: str
    quarantine_reason: QuarantineReason
    quarantine_message: str
    quarantined_at: datetime = Field(default_factory=datetime.utcnow)
    reviewed: bool = False
    reviewer_id: str | None = None
    review_decision: str | None = None
    reviewed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DataQualityReport(BaseModel):
    """Quality report for a dataset or batch."""

    report_id: UUID = Field(default_factory=uuid4)
    dataset_id: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    total_records: int
    valid_records: int
    quarantined_records: int
    duplicate_records: int
    average_quality_score: float = Field(ge=0.0, le=1.0)
    average_relevance_score: float = Field(ge=0.0, le=1.0)
    language_distribution: dict[str, int] = Field(default_factory=dict)
    source_distribution: dict[str, int] = Field(default_factory=dict)
    issues: list[dict[str, Any]] = Field(default_factory=list)


class LakehouseConfig(BaseModel):
    """Configuration for lakehouse storage."""

    raw_bucket: str = "agrimind-raw"
    curated_bucket: str = "agrimind-curated"
    quarantine_bucket: str = "agrimind-quarantine"
    manifests_bucket: str = "agrimind-manifests"
    iceberg_catalog: str = "agrimind_catalog"
    partition_by_date: bool = True
    compression: str = "snappy"
    retention_days_raw: int = 3650
    retention_days_curated: int = 3650
