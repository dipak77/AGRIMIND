"""Query contract for farmer interactions (En/Hi/Mr, multi-modal)."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Language(str, Enum):
    ENGLISH = "en"
    HINDI = "hi"
    MARATHI = "mr"


class QueryModality(str, Enum):
    TEXT = "text"
    VOICE = "voice"
    IMAGE = "image"
    MULTI = "multi"


class GeoPoint(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    accuracy_meters: float | None = Field(None, gt=0)
    district: str | None = None
    state: str | None = None


class Query(BaseModel):
    """Canonical query contract used by gateway, assistant, and orchestrator."""

    query_id: UUID = Field(default_factory=uuid4)
    text: str = Field(..., min_length=1, max_length=4096)
    lang: Language = Field(default=Language.ENGLISH)
    modality: QueryModality = Field(default=QueryModality.TEXT)
    location: GeoPoint | None = None
    user_id: str = Field(..., min_length=1)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    session_id: str | None = None
    image_urls: list[str] | None = None
    audio_url: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}

    @property
    def language(self) -> Language:
        """Alias for SafetyEngine / older call sites."""
        return self.lang

    @property
    def has_image(self) -> bool:
        return self.modality in (QueryModality.IMAGE, QueryModality.MULTI) and bool(
            self.image_urls
        )
