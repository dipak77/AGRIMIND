"""Unit tests for the unified SafetyEngine."""

from agrimind_kernel.contracts import Citation, Language, Query, SafetyLevel, SafetyPolicy
from agrimind_kernel.safety_engine import SafetyEngine, SafetyEvaluationResult


def create_test_query(text: str = "What is crop rotation?", lang: Language = Language.ENGLISH) -> Query:
    return Query(text=text, lang=lang, user_id="test_user")


class TestSafetyEngineInitialization:
    def test_default_policy_has_banned_list(self):
        engine = SafetyEngine()
        assert "ddt" in [c.lower() for c in engine.policy.banned_chemicals]

    def test_custom_policy(self):
        policy = SafetyPolicy(banned_chemicals=["DDT", "Paraquat"])
        engine = SafetyEngine(policy=policy)
        assert engine.policy.banned_chemicals == ["DDT", "Paraquat"]


class TestSafetyEvaluationResult:
    def test_default_values(self):
        result = SafetyEvaluationResult()
        assert result.passed is False
        assert result.safety_level == SafetyLevel.GENERAL


class TestSafetyEngineEvaluate:
    def test_general_query_passes(self):
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

    def test_low_confidence_fails(self):
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
        assert any("Confidence" in r for r in result.reasons)

    def test_banned_chemical_blocks(self):
        engine = SafetyEngine()
        query = create_test_query("Spray advice")
        result = engine.evaluate(
            query=query,
            draft_response="Use monocrotophos 10 ml per liter",
            citations=[],
            confidence=0.99,
        )
        assert result.passed is False
        assert result.banned_content_detected is True

    def test_chemical_requires_citations(self):
        engine = SafetyEngine()
        query = create_test_query("bollworm spray dosage")
        result = engine.evaluate(
            query=query,
            draft_response="Use neem oil as part of IPM.",
            citations=[],
            confidence=0.96,
            safety_level=SafetyLevel.CHEMICAL_DOSAGE,
        )
        assert result.passed is False
        assert result.missing_citations is True

    def test_chemical_with_citation_passes(self):
        engine = SafetyEngine()
        query = create_test_query("bollworm treatment")
        cit = Citation(
            source_id="icar-1",
            source_type="document",
            title="ICAR",
            url_or_path="s3://x",
            checksum="sha256:abc",
            excerpt="IPM practices",
        )
        result = engine.evaluate(
            query=query,
            draft_response="Use IPM and neem-based products per ICAR guidance.",
            citations=[cit],
            confidence=0.96,
            safety_level=SafetyLevel.CHEMICAL_DOSAGE,
        )
        assert result.passed is True

    def test_fallback_response(self):
        engine = SafetyEngine()
        query = create_test_query("dosage for pesticide", lang=Language.ENGLISH)
        fb = engine.create_safe_fallback_response(query, trace_id="t1")
        assert fb.fallback_used is True
        assert fb.confidence <= 0.5
        assert "KVK" in fb.answer or "expert" in fb.answer.lower()
