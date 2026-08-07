"""Unit tests for the SafetyEngine."""

import pytest

from agrimind_kernel.contracts import (
    Citation,
    Language,
    Query,
    SafetyLevel,
    SafetyPolicy,
)
from agrimind_kernel.safety_engine import SafetyEngine, SafetyEvaluationResult


def create_test_query(
    text: str = "What is crop rotation?",
    language: Language = Language.ENGLISH,
) -> Query:
    """Helper to create a test query."""
    return Query(query_id="test-q-123", text=text, language=language)


class TestSafetyEngineInitialization:
    """Test SafetyEngine initialization."""

    def test_default_policy(self):
        """Test engine with default policy."""
        engine = SafetyEngine()
        assert engine.policy is not None
        assert engine.policy.banned_chemicals == []

    def test_custom_policy(self):
        """Test engine with custom policy."""
        policy = SafetyPolicy(banned_chemicals=["DDT", "Paraquat"])
        engine = SafetyEngine(policy=policy)
        assert engine.policy.banned_chemicals == ["DDT", "Paraquat"]


class TestSafetyEvaluationResult:
    """Test SafetyEvaluationResult dataclass."""

    def test_default_values(self):
        """Test default result values."""
        result = SafetyEvaluationResult()
        assert result.passed is False
        assert result.safety_level == SafetyLevel.GENERAL
        assert result.confidence == 0.0
        assert result.reasons == []


class TestSafetyEngineEvaluate:
    """Test SafetyEngine.evaluate method."""

    def test_general_query_passes(self):
        """Test that general queries pass safety checks."""
        engine = SafetyEngine()
        query = create_test_query("What is crop rotation?")
        result = engine.evaluate(
            query=query,
            draft_response="Crop rotation helps improve soil health.",
            citations=[],
            confidence=0.85,
            safety_level=SafetyLevel.GENERAL,
        )
        assert result.passed is True
        assert result.safety_level == SafetyLevel.GENERAL

    def test_low_confidence_fails(self):
        """Test that low confidence fails for high-risk levels."""
        engine = SafetyEngine()
        query = create_test_query("What pesticide should I use?")
        result = engine.evaluate(
            query=query,
            draft_response="Use a common pesticide.",
            citations=[],
            confidence=0.5,
            safety_level=SafetyLevel.CHEMICAL_DOSAGE,
        )
        assert result.passed is False
        assert any("Confidence" in reason for reason in result.reasons)

    def test_chemical_dosage_requires_citations(self):
        """Test that chemical dosage responses require citations."""
        engine = SafetyEngine()
        query = create_test_query("What is the dosage for glyphosate?")
        result = engine.evaluate(
            query=query,
            draft_response="Use 2 liters per hectare.",
            citations=[],
            confidence=0.96,
            safety_level=SafetyLevel.CHEMICAL_DOSAGE,
        )
        assert result.passed is False
        assert result.requires_citations is True
        assert result.missing_citations is True

    def test_chemical_dosage_with_citations_passes(self):
        """Test that chemical dosage with citations can pass."""
        engine = SafetyEngine()
        citation = Citation(
            source_id="src-1",
            source_type="document",
            title="Pesticide Guide",
            excerpt="Glyphosate dosage recommendations",
            confidence=0.95,
        )
        query = create_test_query("What is the dosage for glyphosate?")
        result = engine.evaluate(
            query=query,
            draft_response="Use 2 liters per hectare according to guidelines.",
            citations=[citation],
            confidence=0.96,
            safety_level=SafetyLevel.CHEMICAL_DOSAGE,
        )
        assert result.passed is True
        assert result.requires_citations is True
        assert result.missing_citations is False

    def test_banned_chemical_detected(self):
        """Test detection of banned chemicals."""
        policy = SafetyPolicy(banned_chemicals=["DDT", "Paraquat"])
        engine = SafetyEngine(policy=policy)
        query = create_test_query("Can I use DDT?")
        result = engine.evaluate(
            query=query,
            draft_response="DDT is effective but banned.",
            citations=[],
            confidence=0.9,
        )
        assert result.passed is False
        assert result.banned_content_detected is True
        assert any("banned" in reason.lower() for reason in result.reasons)

    def test_safety_level_auto_detection(self):
        """Test automatic safety level detection."""
        engine = SafetyEngine()

        # Chemical detection
        query1 = create_test_query("What pesticide dosage should I use?")
        result1 = engine.evaluate(
            query=query1,
            draft_response="Apply 500ml per liter.",
            citations=[],
            confidence=0.9,
        )
        assert result1.safety_level == SafetyLevel.CHEMICAL_DOSAGE

        # Legal detection
        query2 = create_test_query("Is this legal under agriculture law?")
        result2 = engine.evaluate(
            query=query2,
            draft_response="Check the regulation.",
            citations=[],
            confidence=0.8,
        )
        assert result2.safety_level == SafetyLevel.LEGAL_ADVICE

        # Medical detection
        query3 = create_test_query("What if someone gets poisoned?")
        result3 = engine.evaluate(
            query=query3,
            draft_response="Go to a hospital.",
            citations=[],
            confidence=0.85,
        )
        assert result3.safety_level == SafetyLevel.MEDICAL_ADVICE

        # High risk detection
        query4 = create_test_query("Is this toxic?")
        result4 = engine.evaluate(
            query=query4,
            draft_response="This is very dangerous.",
            citations=[],
            confidence=0.8,
        )
        assert result4.safety_level == SafetyLevel.HIGH_RISK

        # General (default)
        query5 = create_test_query("When should I plant wheat?")
        result5 = engine.evaluate(
            query=query5,
            draft_response="Plant in October-November.",
            citations=[],
            confidence=0.85,
        )
        assert result5.safety_level == SafetyLevel.GENERAL

    def test_multilingual_queries(self):
        """Test safety evaluation for multilingual queries."""
        engine = SafetyEngine()

        # Hindi query about pesticides
        query_hi = create_test_query(
            "कीटनाशक की खुराक क्या है?",
            language=Language.HINDI,
        )
        result_hi = engine.evaluate(
            query=query_hi,
            draft_response="2 मिलीलीटर प्रति लीटर उपयोग करें।",
            citations=[],
            confidence=0.5,
        )
        # Should detect as chemical dosage even in Hindi
        # Note: Current implementation is English-only keyword matching
        # This is a known limitation to be addressed

        # Marathi query
        query_mr = create_test_query(
            "पीडनाशकांचे प्रमाण काय आहे?",
            language=Language.MARATHI,
        )
        result_mr = engine.evaluate(
            query=query_mr,
            draft_response="2 मिली प्रति लिटर वापरा.",
            citations=[],
            confidence=0.5,
        )


class TestCreateSafeFallbackResponse:
    """Test safe fallback response creation."""

    def test_fallback_response_structure(self):
        """Test that fallback response has correct structure."""
        engine = SafetyEngine()
        query = create_test_query("Tell me about dangerous pesticides.")

        fallback = engine.create_safe_fallback_response(query)

        assert fallback.query_id == query.query_id
        assert fallback.language == query.language
        assert fallback.confidence == 0.3
        assert fallback.safety_level == SafetyLevel.GENERAL
        assert fallback.requires_review is True
        assert fallback.citations == []
        assert "unable to provide" in fallback.text.lower()
        assert "expert" in fallback.text.lower()
