"""
Query contract for AGRIMIND.

Defines the standard structure for all farmer queries entering the system.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, ClassVar
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class QueryModality(str, Enum):
    """Supported query modalities."""

    TEXT = "text"
    VOICE = "voice"
    IMAGE = "image"
    MULTI = "multi"


class GeoPoint(BaseModel):
    """Geographic location with latitude and longitude."""

    latitude: float = Field(..., ge=-90, le=90, description="Latitude in degrees")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude in degrees")
    accuracy_meters: float | None = Field(None, gt=0, description="GPS accuracy in meters")

    class Config:
        json_schema_extra: ClassVar[dict[str, Any]] = {
            "example": {
                "latitude": 19.0760,
                "longitude": 72.8777,
                "accuracy_meters": 10.0,
            }
        }


class Query(BaseModel):
    """
    Standard query contract for all farmer interactions.

    Every query must have a unique ID, text content, language specification,
    and optional context like location and user identity.
    """

    query_id: UUID = Field(default_factory=uuid4, description="Unique identifier for this query")
    text: str = Field(..., min_length=1, max_length=4096, description="Query text")
    lang: str = Field(..., pattern="^(en|hi|mr)$", description="Language code: en, hi, or mr")
    modality: QueryModality = Field(default=QueryModality.TEXT, description="Input modality")
    location: GeoPoint | None = Field(
        None, description="Optional farmer location for localized advice"
    )
    user_id: str = Field(..., min_length=1, description="User identifier")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Query timestamp")
    session_id: str | None = Field(None, description="Optional session identifier")
    image_urls: list[str] | None = Field(
        None, description="URLs to uploaded images (for image/modality)"
    )
    audio_url: str | None = Field(None, description="URL to uploaded audio (for voice modality)")

    class Config:
        json_schema_extra: ClassVar[dict[str, Any]] = {
            "example": {
                "query_id": "550e8400-e29b-41d4-a716-446655440000",
                "text": "कपाशीवर बोंडअळी आली आहे, काय करावे?",
                "lang": "mr",
                "modality": "text",
                "location": {"latitude": 19.0760, "longitude": 72.8777},
                "user_id": "farmer_12345",
                "timestamp": "2026-01-15T10:30:00Z",
            }
        }

    @property
    def is_multilingual(self) -> bool:
        """Check if query is in non-English language."""
        return self.lang != "en"

    @property
    def has_location(self) -> bool:
        """Check if query includes location context."""
        return self.location is not None

    @property
    def has_image(self) -> bool:
        """Check if query includes images."""
        return self.modality in (QueryModality.IMAGE, QueryModality.MULTI) and bool(self.image_urls)
