"""Safety engine for evaluating content against safety policies."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agrimind_kernel.contracts import (
    SAFETY_CONFIDENCE_THRESHOLDS,
    Citation,
    Query,
    Response,
    SafetyLevel,
    SafetyPolicy,
)


@dataclass
class SafetyEvaluationResult:
    """Result of safety evaluation."""

    passed: bool = field(default=False)
    safety_level: SafetyLevel = field(default=SafetyLevel.GENERAL)
    confidence: float = field(default=0.0)
    reasons: list[str] = field(default_factory=list)
    requires_citations: bool = field(default=False)
    missing_citations: bool = field(default=False)
    banned_content_detected: bool = field(default=False)


class SafetyEngine:
    """Engine for evaluating content safety."""

    def __init__(self, policy: SafetyPolicy | None = None) -> None:
        self.policy = policy or SafetyPolicy()

    def evaluate(
        self,
        query: Query,
        draft_response: str,
        citations: list[Citation],
        confidence: float,
        safety_level: SafetyLevel | None = None,
    ) -> SafetyEvaluationResult:
        """
        Evaluate a draft response for safety compliance.

        Args:
            query: The original user query
            draft_response: The generated response text
            citations: List of citations supporting the response
            confidence: Confidence score of the response
            safety_level: Optional pre-determined safety level

        Returns:
            SafetyEvaluationResult with pass/fail and reasons
        """
        reasons: list[str] = []
        passed = True

        # Determine safety level if not provided
        if safety_level is None:
            safety_level = self._detect_safety_level(query.text, draft_response)

        # Get minimum confidence threshold for this safety level
        min_confidence = SAFETY_CONFIDENCE_THRESHOLDS.get(safety_level, 0.7)

        # Check 1: Confidence threshold
        if confidence < min_confidence:
            passed = False
            reasons.append(
                f"Confidence {confidence:.2f} below threshold {min_confidence:.2f} "
                f"for safety level {safety_level.value}"
            )

        # Check 2: Citation requirements
        requires_citations = safety_level in self.policy.require_citations_for_level
        missing_citations = requires_citations and len(citations) == 0

        if missing_citations:
            passed = False
            reasons.append(
                f"Safety level {safety_level.value} requires citations but none provided"
            )

        # Check 3: Banned chemicals
        banned_content_detected = self._check_banned_chemicals(draft_response)
        if banned_content_detected:
            passed = False
            reasons.append("Response contains banned chemicals")

        # Check 4: Max confidence for unsafe content
        if not passed and confidence > self.policy.max_confidence_for_unsafe:
            reasons.append(
                f"High confidence {confidence:.2f} on unsafe content is dangerous"
            )

        return SafetyEvaluationResult(
            passed=passed,
            safety_level=safety_level,
            confidence=confidence,
            reasons=reasons,
            requires_citations=requires_citations,
            missing_citations=missing_citations,
            banned_content_detected=banned_content_detected,
        )

    def _detect_safety_level(self, query_text: str, response_text: str) -> SafetyLevel:
        """Detect safety level from query and response content."""
        combined_text = f"{query_text} {response_text}".lower()

        # Chemical/dosage detection
        chemical_keywords = [
            "pesticide",
            "insecticide",
            "fungicide",
            "herbicide",
            "dosage",
            "spray",
            "concentration",
            "ml per liter",
            "gm per hectare",
        ]
        if any(kw in combined_text for kw in chemical_keywords):
            return SafetyLevel.CHEMICAL_DOSAGE

        # Legal advice detection
        legal_keywords = ["legal", "law", "regulation", "compliance", "liability"]
        if any(kw in combined_text for kw in legal_keywords):
            return SafetyLevel.LEGAL_ADVICE

        # Medical advice detection (human health)
        medical_keywords = ["poisoning", "health hazard", "medical", "doctor", "hospital"]
        if any(kw in combined_text for kw in medical_keywords):
            return SafetyLevel.MEDICAL_ADVICE

        # High risk detection
        high_risk_keywords = ["toxic", "dangerous", "deadly", "hazardous", "warning"]
        if any(kw in combined_text for kw in high_risk_keywords):
            return SafetyLevel.HIGH_RISK

        return SafetyLevel.GENERAL

    def _check_banned_chemicals(self, text: str) -> bool:
        """Check if text contains banned chemicals."""
        text_lower = text.lower()
        return any(
            chemical.lower() in text_lower for chemical in self.policy.banned_chemicals
        )

    def create_safe_fallback_response(self, query: Query) -> Response:
        """Create a safe fallback response when safety checks fail."""
        import uuid
        from datetime import datetime

        return Response(
            response_id=str(uuid.uuid4()),
            query_id=query.query_id,
            text=(
                "I'm unable to provide specific advice on this topic without more verified "
                "information. For questions about pesticides, dosages, or treatments, please "
                "consult a certified agricultural expert or your local Krishi Vigyan Kendra."
            ),
            language=query.language,
            confidence=0.3,
            safety_level=SafetyLevel.GENERAL,
            citations=[],
            requires_review=True,
            model_version="fallback-0.1.0",
            timestamp=datetime.utcnow(),
        )
