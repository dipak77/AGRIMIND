"""
Unit tests for kernel contracts.
"""

from uuid import UUID

import pytest
from pydantic import ValidationError

from kernel.contracts.query import GeoPoint, Query, QueryModality
from kernel.contracts.response import Citation, Response
from kernel.contracts.safety import (
    SAFETY_CONFIDENCE_THRESHOLDS,
    SafetyCheckResult,
    SafetyLevel,
    SafetyPolicy,
    get_safety_level_for_query,
)


class TestGeoPoint:
    """Tests for GeoPoint contract."""

    def test_valid_coordinates(self):
        """Test valid latitude and longitude."""
        point = GeoPoint(latitude=19.0760, longitude=72.8777)
        assert point.latitude == 19.0760
        assert point.longitude == 72.8777
        assert point.accuracy_meters is None

    def test_coordinates_with_accuracy(self):
        """Test coordinates with accuracy."""
        point = GeoPoint(latitude=19.0760, longitude=72.8777, accuracy_meters=10.0)
        assert point.accuracy_meters == 10.0

    def test_invalid_latitude_high(self):
        """Test that latitude > 90 raises validation error."""
        with pytest.raises(ValidationError):
            GeoPoint(latitude=91.0, longitude=0.0)

    def test_invalid_latitude_low(self):
        """Test that latitude < -90 raises validation error."""
        with pytest.raises(ValidationError):
            GeoPoint(latitude=-91.0, longitude=0.0)

    def test_invalid_longitude_high(self):
        """Test that longitude > 180 raises validation error."""
        with pytest.raises(ValidationError):
            GeoPoint(latitude=0.0, longitude=181.0)


class TestQuery:
    """Tests for Query contract."""

    def test_minimal_valid_query(self):
        """Test minimal valid query."""
        query = Query(text="What crops grow in Maharashtra?", lang="en", user_id="user123")
        assert isinstance(query.query_id, UUID)
        assert query.text == "What crops grow in Maharashtra?"
        assert query.lang == "en"
        assert query.modality == QueryModality.TEXT
        assert query.location is None

    def test_query_with_location(self):
        """Test query with location context."""
        query = Query(
            text="What should I plant here?",
            lang="mr",
            user_id="farmer_456",
            location=GeoPoint(latitude=19.0760, longitude=72.8777),
        )
        assert query.has_location is True
        assert query.location.latitude == 19.0760

    def test_query_multilingual_marathi(self):
        """Test Marathi query."""
        query = Query(
            text="कपाशीवर बोंडअळी आली आहे, काय करावे?",
            lang="mr",
            user_id="farmer_789",
        )
        assert query.is_multilingual is True
        assert query.lang == "mr"

    def test_query_multilingual_hindi(self):
        """Test Hindi query."""
        query = Query(
            text="कपासी में इल्ली लग गई है, क्या करें?",
            lang="hi",
            user_id="farmer_101",
        )
        assert query.is_multilingual is True
        assert query.lang == "hi"

    def test_invalid_language_code(self):
        """Test that invalid language code raises validation error."""
        with pytest.raises(ValidationError):
            Query(text="Test", lang="fr", user_id="user123")

    def test_empty_text(self):
        """Test that empty text raises validation error."""
        with pytest.raises(ValidationError):
            Query(text="", lang="en", user_id="user123")

    def test_query_with_image(self):
        """Test query with image URLs."""
        query = Query(
            text="What disease is this?",
            lang="en",
            user_id="user123",
            modality=QueryModality.IMAGE,
            image_urls=["s3://bucket/image1.jpg"],
        )
        assert query.has_image is True
        assert query.modality == QueryModality.IMAGE


class TestCitation:
    """Tests for Citation contract."""

    def test_minimal_citation(self):
        """Test minimal citation."""
        citation = Citation(
            source_id="test-source-1",
            source_type="document",
            url_or_path="s3://bucket/doc.pdf",
            checksum="sha256:abc123",
        )
        assert citation.source_id == "test-source-1"
        assert citation.span is None
        assert citation.license is None

    def test_full_citation(self):
        """Test citation with all fields."""
        citation = Citation(
            source_id="icar-manual-2024",
            source_type="document",
            url_or_path="s3://agrimind-data/icar-cotton.pdf",
            checksum="sha256:def456",
            span="Section 4.2: Bollworm Management",
            license="CC-BY-4.0",
        )
        assert citation.span == "Section 4.2: Bollworm Management"
        assert citation.license == "CC-BY-4.0"


class TestResponse:
    """Tests for Response contract."""

    def test_minimal_response(self):
        """Test minimal valid response."""
        from uuid import uuid4

        query_id = uuid4()
        response = Response(
            query_id=query_id,
            answer="Use IPM methods for bollworm control.",
            lang="en",
            confidence=0.92,
            model_version="agrimind-7b-v1.0.3",
            trace_id="trace123",
        )
        assert response.query_id == query_id
        assert response.confidence == 0.92
        assert response.citations == []
        assert response.has_citations is False

    def test_response_with_citations(self):
        """Test response with citations."""
        from uuid import uuid4

        query_id = uuid4()
        citation = Citation(
            source_id="source1",
            source_type="document",
            url_or_path="s3://bucket/doc.pdf",
            checksum="sha256:abc",
        )
        response = Response(
            query_id=query_id,
            answer="Use IPM methods.",
            lang="en",
            confidence=0.92,
            model_version="agrimind-7b-v1",
            trace_id="trace123",
            citations=[citation],
        )
        assert response.has_citations is True
        assert len(response.citations) == 1

    def test_high_confidence_response(self):
        """Test high confidence response."""
        from uuid import uuid4

        response = Response(
            query_id=uuid4(),
            answer="Answer",
            lang="en",
            confidence=0.90,
            model_version="v1",
            trace_id="t1",
        )
        assert response.is_high_confidence is True

    def test_low_confidence_requires_review(self):
        """Test that low confidence response requires review."""
        from uuid import uuid4

        response = Response(
            query_id=uuid4(),
            answer="Answer",
            lang="en",
            confidence=0.50,
            model_version="v1",
            trace_id="t1",
        )
        assert response.requires_review is True


class TestSafetyLevel:
    """Tests for SafetyLevel enum and thresholds."""

    def test_safety_levels_exist(self):
        """Test that all safety levels are defined."""
        assert SafetyLevel.GENERAL.value == "general"
        assert SafetyLevel.PEST_TREATMENT.value == "pest_treatment"
        assert SafetyLevel.CHEMICAL_DOSAGE.value == "chemical_dosage"
        assert SafetyLevel.LEGAL_SCHEME.value == "legal_scheme"
        assert SafetyLevel.WEATHER_ACTION.value == "weather_action"
        assert SafetyLevel.HEALTH_CLAIM.value == "health_claim"

    def test_confidence_thresholds_defined(self):
        """Test that confidence thresholds are defined for all levels."""
        assert SafetyLevel.GENERAL in SAFETY_CONFIDENCE_THRESHOLDS
        assert SafetyLevel.CHEMICAL_DOSAGE in SAFETY_CONFIDENCE_THRESHOLDS
        assert SAFETY_CONFIDENCE_THRESHOLDS[SafetyLevel.CHEMICAL_DOSAGE] == 0.95
        assert SAFETY_CONFIDENCE_THRESHOLDS[SafetyLevel.GENERAL] == 0.70


class TestSafetyPolicy:
    """Tests for SafetyPolicy contract."""

    def test_default_policy(self):
        """Test default safety policy values."""
        policy = SafetyPolicy()
        assert policy.allow_chemical_advice is False
        assert policy.require_citation_for_dosage is True
        assert policy.block_banned_chemicals is True
        assert policy.banned_chemicals == []

    def test_custom_policy(self):
        """Test custom safety policy."""
        policy = SafetyPolicy(
            allow_chemical_advice=True,
            blocked_keywords=["poison", "suicide"],
            banned_chemicals=["DDT", "Endosulfan"],
        )
        assert policy.allow_chemical_advice is True
        assert "DDT" in policy.banned_chemicals


class TestSafetyCheckResult:
    """Tests for SafetyCheckResult contract."""

    def test_passed_check(self):
        """Test passed safety check."""
        result = SafetyCheckResult(
            passed=True,
            safety_level=SafetyLevel.GENERAL,
            confidence_threshold=0.70,
        )
        assert result.should_block is False
        assert result.should_fallback is False

    def test_blocked_check(self):
        """Test blocked safety check."""
        result = SafetyCheckResult(
            passed=False,
            safety_level=SafetyLevel.CHEMICAL_DOSAGE,
            confidence_threshold=0.95,
            blocked_reason="Unsafe chemical advice detected",
            suggested_action="block",
        )
        assert result.should_block is True

    def test_review_required(self):
        """Test safety check requiring human review."""
        result = SafetyCheckResult(
            passed=True,
            safety_level=SafetyLevel.PEST_TREATMENT,
            confidence_threshold=0.85,
            requires_human_review=True,
        )
        assert result.should_review is True


class TestGetSafetyLevelForQuery:
    """Tests for safety level detection heuristic."""

    def test_general_query(self):
        """Test general advisory query."""
        level = get_safety_level_for_query("What crops grow in June?")
        assert level == SafetyLevel.GENERAL

    def test_chemical_dosage_query_english(self):
        """Test chemical dosage query in English."""
        level = get_safety_level_for_query("What is the dosage of pesticide per liter?")
        assert level == SafetyLevel.CHEMICAL_DOSAGE

    def test_treatment_query_marathi(self):
        """Test treatment query in Marathi."""
        level = get_safety_level_for_query("बोंडअळी नियंत्रण काय करावे?")
        assert level == SafetyLevel.PEST_TREATMENT

    def test_scheme_query_hindi(self):
        """Test government scheme query in Hindi."""
        level = get_safety_level_for_query("सरकारी योजना क्या है?")
        assert level == SafetyLevel.LEGAL_SCHEME

    def test_weather_query(self):
        """Test weather-related query."""
        level = get_safety_level_for_query("When should I sow based on rain forecast?")
        assert level == SafetyLevel.WEATHER_ACTION
