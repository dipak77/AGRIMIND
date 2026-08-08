"""Safety engine: confidence gates, citations, banned chemicals, injection."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from agrimind_kernel.contracts import (
    SAFETY_CONFIDENCE_THRESHOLDS,
    Citation,
    Language,
    Query,
    Response,
    SafetyLevel,
    SafetyPolicy,
)

DOSAGE_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(ml|g|gm|kg|l)\s*(per|/)\s*(l|liter|litre|ha|hectare|acre)",
    re.IGNORECASE,
)
INJECTION_PATTERNS = (
    "ignore previous instructions",
    "system prompt",
    "jailbreak",
    "disregard all rules",
)


@dataclass
class SafetyEvaluationResult:
    passed: bool = False
    safety_level: SafetyLevel = SafetyLevel.GENERAL
    confidence: float = 0.0
    reasons: list[str] = field(default_factory=list)
    requires_citations: bool = False
    missing_citations: bool = False
    banned_content_detected: bool = False
    flags: list[str] = field(default_factory=list)
    suggested_action: str = "proceed"


class SafetyEngine:
    """Evaluate draft answers before they reach the farmer."""

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
        reasons: list[str] = []
        flags: list[str] = []
        passed = True
        suggested = "proceed"

        if safety_level is None:
            safety_level = self._detect_safety_level(query.text, draft_response)

        min_confidence = SAFETY_CONFIDENCE_THRESHOLDS.get(safety_level, 0.7)
        if confidence < min_confidence:
            passed = False
            flags.append("low_confidence")
            reasons.append(
                f"Confidence {confidence:.2f} below threshold {min_confidence:.2f} "
                f"for safety level {safety_level.value}"
            )
            suggested = "fallback"

        requires_citations = safety_level in self.policy.require_citations_for_level
        missing_citations = requires_citations and len(citations) == 0
        if missing_citations:
            passed = False
            flags.append("missing_citations")
            reasons.append(f"Safety level {safety_level.value} requires citations")
            suggested = "fallback"

        banned = self._check_banned_chemicals(f"{query.text} {draft_response}")
        if banned:
            passed = False
            flags.append("banned_chemical")
            reasons.append("Response or query mentions a banned chemical")
            suggested = "block"

        if self.policy.block_prompt_injection and self._check_injection(
            f"{query.text} {draft_response}"
        ):
            passed = False
            flags.append("prompt_injection")
            reasons.append("Prompt injection pattern detected")
            suggested = "block"

        if (
            self.policy.require_citation_for_dosage
            and DOSAGE_PATTERN.search(draft_response)
            and len(citations) == 0
        ):
            passed = False
            flags.append("dosage_without_citation")
            reasons.append("Numeric dosage without citation is blocked")
            suggested = "block"

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
            banned_content_detected=banned,
            flags=flags,
            suggested_action=suggested if not passed else "proceed",
        )

    def _detect_safety_level(self, query_text: str, response_text: str) -> SafetyLevel:
        combined = f"{query_text} {response_text}".lower()

        chemical_keywords = [
            "pesticide",
            "insecticide",
            "fungicide",
            "herbicide",
            "dosage",
            "dose",
            "spray",
            "concentration",
            "ml per",
            "gm per",
            "फवारणी",
            "खत मात्रा",
        ]
        if any(kw in combined for kw in chemical_keywords) or DOSAGE_PATTERN.search(combined):
            return SafetyLevel.CHEMICAL_DOSAGE

        treatment = [
            "treatment",
            "bollworm",
            "pest",
            "disease",
            "रोग",
            "कीड",
            "नियंत्रण",
            "ipm",
        ]
        if any(kw in combined for kw in treatment):
            return SafetyLevel.PEST_TREATMENT

        legal = ["scheme", "subsidy", "loan", "legal", "योजना", "अनुदान", "eligibility"]
        if any(kw in combined for kw in legal):
            return SafetyLevel.LEGAL_SCHEME

        weather = ["weather", "rain", "sow", "harvest", "हवामान", "पाऊस"]
        if any(kw in combined for kw in weather):
            return SafetyLevel.WEATHER_ACTION

        medical = ["poisoning", "hospital", "doctor", "medical", "health hazard"]
        if any(kw in combined for kw in medical):
            return SafetyLevel.MEDICAL_ADVICE

        high_risk = ["toxic", "deadly", "hazardous", "suicide"]
        if any(kw in combined for kw in high_risk):
            return SafetyLevel.HIGH_RISK

        return SafetyLevel.GENERAL

    def _check_banned_chemicals(self, text: str) -> bool:
        lower = text.lower()
        return any(c.lower() in lower for c in self.policy.banned_chemicals)

    def _check_injection(self, text: str) -> bool:
        lower = text.lower()
        return any(p in lower for p in INJECTION_PATTERNS)

    def create_safe_fallback_response(
        self,
        query: Query,
        *,
        trace_id: str | None = None,
        reasons: list[str] | None = None,
    ) -> Response:
        lang = query.lang if isinstance(query.lang, Language) else Language(str(query.lang))
        if lang == Language.MARATHI:
            text = (
                "सुरक्षिततेसाठी मी विशिष्ट रासायनिक सल्ला देऊ शकत नाही. "
                "कृपया स्थानिक कृषी अधिकारी किंवा कृषी विज्ञान केंद्र (KVK) शी संपर्क साधा."
            )
        elif lang == Language.HINDI:
            text = (
                "सुरक्षा के लिए मैं विशिष्ट रासायनिक सलाह नहीं दे सकता। "
                "कृपया स्थानीय कृषि अधिकारी या कृषि विज्ञान केंद्र से संपर्क करें।"
            )
        else:
            text = (
                "I'm unable to provide this advice safely without verified sources. "
                "For pesticides, dosages, or treatments, consult a certified agricultural "
                "expert or your local Krishi Vigyan Kendra (KVK)."
            )
        return Response(
            response_id=str(uuid.uuid4()),
            query_id=query.query_id,
            answer=text,
            lang=lang,
            confidence=0.3,
            safety_level=SafetyLevel.GENERAL,
            citations=[],
            requires_review=True,
            fallback_used=True,
            action="fallback_human",
            model_version="fallback-0.1.0",
            trace_id=trace_id or str(uuid.uuid4()),
            safety_flags=list(reasons or ["safety_fallback"]),
            timestamp=datetime.now(UTC),
        )
