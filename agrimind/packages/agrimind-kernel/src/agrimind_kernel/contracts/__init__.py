"""Core data contracts for AGRIMIND platform."""

from __future__ import annotations

__all__ = [
    "Language",
    "SafetyLevel",
    "SAFETY_CONFIDENCE_THRESHOLDS",
    "Citation",
    "GeoPoint",
    "Query",
    "Response",
    "SafetyPolicy",
]


from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class Language(str, Enum):
    """Supported languages."""

    ENGLISH = "en"
    HINDI = "hi"
    MARATHI = "mr"


class SafetyLevel(str, Enum):
    """Safety classification levels."""

    GENERAL = "general"
    CHEMICAL_DOSAGE = "chemical_dosage"
    LEGAL_ADVICE = "legal_advice"
    MEDICAL_ADVICE = "medical_advice"
    HIGH_RISK = "high_risk"


# Confidence thresholds by safety level
SAFETY_CONFIDENCE_THRESHOLDS: dict[SafetyLevel, float] = {
    SafetyLevel.GENERAL: 0.7,
    SafetyLevel.CHEMICAL_DOSAGE: 0.95,
    SafetyLevel.LEGAL_ADVICE: 0.95,
    SafetyLevel.MEDICAL_ADVICE: 0.95,
    SafetyLevel.HIGH_RISK: 0.98,
}


class Citation(BaseModel):
    """Citation for grounded responses."""

    source_id: str = Field(..., description="Unique identifier for the source")
    source_type: Literal["document", "web", "knowledge_graph", "expert"] = Field(
        ..., description="Type of source"
    )
    title: str = Field(..., description="Title of the source")
    url: str | None = Field(None, description="URL if available")
    excerpt: str = Field(..., description="Relevant excerpt from the source")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in this citation")


class GeoPoint(BaseModel):
    """Geographic coordinate."""

    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude in degrees")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Longitude in degrees")


class Query(BaseModel):
    """User query contract."""

    query_id: str = Field(..., description="Unique query identifier")
    text: str = Field(..., min_length=1, description="Query text")
    language: Language = Field(default=Language.ENGLISH, description="Query language")
    location: GeoPoint | None = Field(None, description="Optional user location")
    context: dict[str, Any] = Field(default_factory=dict, description="Additional context")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Query timestamp")


class Response(BaseModel):
    """System response contract."""

    response_id: str = Field(..., description="Unique response identifier")
    query_id: str = Field(..., description="Reference to original query")
    text: str = Field(..., description="Response text")
    language: Language = Field(..., description="Response language")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Overall confidence")
    safety_level: SafetyLevel = Field(..., description="Safety classification")
    citations: list[Citation] = Field(default_factory=list, description="Supporting citations")
    requires_review: bool = Field(
        default=False, description="Flag indicating human review needed"
    )
    model_version: str = Field(..., description="Model version used")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class SafetyPolicy(BaseModel):
    """Safety policy configuration."""

    banned_chemicals: list[str] = Field(
        default_factory=list, description="List of banned chemicals"
    )
    max_confidence_for_unsafe: float = Field(
        default=0.3, ge=0.0, le=1.0, description="Max confidence for unsafe content"
    )
    require_citations_for_level: list[SafetyLevel] = Field(
        default=[SafetyLevel.CHEMICAL_DOSAGE, SafetyLevel.HIGH_RISK],
        description="Safety levels requiring citations",
    )
