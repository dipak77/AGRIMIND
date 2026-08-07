"""Unit tests for kernel contracts."""

import uuid
from datetime import datetime

import pytest
from pydantic import ValidationError

from agrimind_kernel.contracts import (
    Citation,
    GeoPoint,
    Language,
    Query,
    Response,
    SafetyLevel,
    SAFETY_CONFIDENCE_THRESHOLDS,
)


class TestLanguage:
    """Test Language enum."""

    def test_language_values(self):
        """Test that language enum has correct values."""
        assert Language.ENGLISH.value == "en"
        assert Language.HINDI.value == "hi"
        assert Language.MARATHI.value == "mr"

    def test_language_from_string(self):
        """Test creating language from string."""
        assert Language("en") == Language.ENGLISH
        assert Language("hi") == Language.HINDI
        assert Language("mr") == Language.MARATHI

    def test_invalid_language(self):
        """Test that invalid language raises ValueError."""
        with pytest.raises(ValueError):
            Language("fr")


class TestSafetyLevel:
    """Test SafetyLevel enum."""

    def test_safety_level_values(self):
        """Test that safety level enum has correct values."""
        assert SafetyLevel.GENERAL.value == "general"
        assert SafetyLevel.CHEMICAL_DOSAGE.value == "chemical_dosage"
        assert SafetyLevel.HIGH_RISK.value == "high_risk"

    def test_confidence_thresholds_exist(self):
        """Test that confidence thresholds are defined for all levels."""
        for level in SafetyLevel:
            assert level in SAFETY_CONFIDENCE_THRESHOLDS
            threshold = SAFETY_CONFIDENCE_THRESHOLDS[level]
            assert 0.0 <= threshold <= 1.0


class TestGeoPoint:
    """Test GeoPoint model."""

    def test_valid_coordinates(self):
        """Test valid geographic coordinates."""
        point = GeoPoint(latitude=40.7128, longitude=-74.0060)
        assert point.latitude == 40.7128
        assert point.longitude == -74.0060

    def test_boundary_values(self):
        """Test boundary values for coordinates."""
        # Valid boundaries
        point1 = GeoPoint(latitude=90.0, longitude=180.0)
        assert point1.latitude == 90.0
        point2 = GeoPoint(latitude=-90.0, longitude=-180.0)
        assert point2.latitude == -90.0

    def test_invalid_latitude(self):
        """Test that invalid latitude raises ValidationError."""
        with pytest.raises(ValidationError):
            GeoPoint(latitude=91.0, longitude=0.0)
        with pytest.raises(ValidationError):
            GeoPoint(latitude=-91.0, longitude=0.0)

    def test_invalid_longitude(self):
        """Test that invalid longitude raises ValidationError."""
        with pytest.raises(ValidationError):
            GeoPoint(latitude=0.0, longitude=181.0)
        with pytest.raises(ValidationError):
            GeoPoint(latitude=0.0, longitude=-181.0)


class TestCitation:
    """Test Citation model."""

    def test_valid_citation(self):
        """Test creating a valid citation."""
        citation = Citation(
            source_id="src-123",
            source_type="document",
            title="Agricultural Best Practices",
            url="https://example.com/doc",
            excerpt="Best practices for crop rotation",
            confidence=0.95,
        )
        assert citation.source_id == "src-123"
        assert citation.source_type == "document"
        assert citation.confidence == 0.95

    def test_citation_without_url(self):
        """Test citation without URL."""
        citation = Citation(
            source_id="src-456",
            source_type="knowledge_graph",
            title="Pest Control Knowledge",
            excerpt="Integrated pest management strategies",
            confidence=0.88,
        )
        assert citation.url is None

    def test_invalid_source_type(self):
        """Test that invalid source type raises ValidationError."""
        with pytest.raises(ValidationError):
            Citation(
                source_id="src-789",
                source_type="invalid_type",
                title="Test",
                excerpt="Test excerpt",
                confidence=0.9,
            )

    def test_confidence_bounds(self):
        """Test confidence value bounds."""
        with pytest.raises(ValidationError):
            Citation(
                source_id="src-111",
                source_type="web",
                title="Test",
                excerpt="Test",
                confidence=1.5,
            )
        with pytest.raises(ValidationError):
            Citation(
                source_id="src-222",
                source_type="web",
                title="Test",
                excerpt="Test",
                confidence=-0.1,
            )


class TestQuery:
    """Test Query model."""

    def test_minimal_query(self):
        """Test creating a minimal valid query."""
        query = Query(query_id="q-123", text="What is crop rotation?")
        assert query.query_id == "q-123"
        assert query.text == "What is crop rotation?"
        assert query.language == Language.ENGLISH
        assert query.location is None

    def test_full_query(self):
        """Test creating a query with all fields."""
        location = GeoPoint(latitude=19.0760, longitude=72.8777)
        query = Query(
            query_id="q-456",
            text="कापूस पिकासाठी खत शिफारस?",
            language=Language.HINDI,
            location=location,
            context={"crop": "cotton", "season": "kharif"},
        )
        assert query.language == Language.HINDI
        assert query.location.latitude == 19.0760
        assert query.context["crop"] == "cotton"

    def test_empty_text_fails(self):
        """Test that empty text raises ValidationError."""
        with pytest.raises(ValidationError):
            Query(query_id="q-789", text="")


class TestResponse:
    """Test Response model."""

    def test_minimal_response(self):
        """Test creating a minimal valid response."""
        response = Response(
            response_id="r-123",
            query_id="q-123",
            text="Crop rotation helps improve soil health.",
            language=Language.ENGLISH,
            confidence=0.85,
            safety_level=SafetyLevel.GENERAL,
            model_version="v1.0.0",
        )
        assert response.response_id == "r-123"
        assert response.citations == []
        assert response.requires_review is False

    def test_response_with_citations(self):
        """Test response with citations."""
        citation = Citation(
            source_id="src-123",
            source_type="document",
            title="Agricultural Guide",
            excerpt="Crop rotation benefits",
            confidence=0.9,
        )
        response = Response(
            response_id="r-456",
            query_id="q-456",
            text="According to experts, crop rotation improves yield.",
            language=Language.ENGLISH,
            confidence=0.88,
            safety_level=SafetyLevel.GENERAL,
            citations=[citation],
            model_version="v1.0.0",
        )
        assert len(response.citations) == 1
        assert response.citations[0].source_id == "src-123"

    def test_requires_review_flag(self):
        """Test requires_review flag."""
        response = Response(
            response_id="r-789",
            query_id="q-789",
            text="Consult an expert for pesticide dosage.",
            language=Language.ENGLISH,
            confidence=0.75,
            safety_level=SafetyLevel.CHEMICAL_DOSAGE,
            requires_review=True,
            model_version="v1.0.0",
        )
        assert response.requires_review is True
        assert response.safety_level == SafetyLevel.CHEMICAL_DOSAGE
