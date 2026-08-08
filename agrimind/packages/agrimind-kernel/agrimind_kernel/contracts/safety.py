"""Safety levels, policies, and check results."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class SafetyLevel(str, Enum):
    GENERAL = "general"
    PEST_TREATMENT = "pest_treatment"
    CHEMICAL_DOSAGE = "chemical_dosage"
    LEGAL_SCHEME = "legal_scheme"
    WEATHER_ACTION = "weather_action"
    HEALTH_CLAIM = "health_claim"
    # Aliases kept for earlier SafetyEngine tests / policy lists
    LEGAL_ADVICE = "legal_advice"
    MEDICAL_ADVICE = "medical_advice"
    HIGH_RISK = "high_risk"


SAFETY_CONFIDENCE_THRESHOLDS: dict[SafetyLevel, float] = {
    SafetyLevel.GENERAL: 0.70,
    SafetyLevel.PEST_TREATMENT: 0.85,
    SafetyLevel.CHEMICAL_DOSAGE: 0.95,
    SafetyLevel.LEGAL_SCHEME: 0.90,
    SafetyLevel.WEATHER_ACTION: 0.85,
    SafetyLevel.HEALTH_CLAIM: 0.90,
    SafetyLevel.LEGAL_ADVICE: 0.90,
    SafetyLevel.MEDICAL_ADVICE: 0.90,
    SafetyLevel.HIGH_RISK: 0.98,
}


DEFAULT_BANNED_CHEMICALS = [
    "ddt",
    "monocrotophos",
    "endosulfan",
    "lindane",
    "parathion",
    "methyl parathion",
]


class SafetyPolicy(BaseModel):
    banned_chemicals: list[str] = Field(default_factory=lambda: list(DEFAULT_BANNED_CHEMICALS))
    max_confidence_for_unsafe: float = Field(default=0.3, ge=0.0, le=1.0)
    require_citations_for_level: list[SafetyLevel] = Field(
        default_factory=lambda: [
            SafetyLevel.CHEMICAL_DOSAGE,
            SafetyLevel.PEST_TREATMENT,
            SafetyLevel.HIGH_RISK,
            SafetyLevel.LEGAL_SCHEME,
        ]
    )
    block_prompt_injection: bool = True
    require_citation_for_dosage: bool = True


class SafetyCheckResult(BaseModel):
    passed: bool
    safety_level: SafetyLevel
    confidence_threshold: float
    flags: list[str] = Field(default_factory=list)
    blocked_reason: str | None = None
    requires_human_review: bool = False
    suggested_action: str = "proceed"

    @property
    def should_block(self) -> bool:
        return not self.passed or self.suggested_action == "block"
