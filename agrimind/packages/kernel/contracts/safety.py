"""
Safety contracts for AGRIMIND.

Defines safety levels, policies, and check results to ensure farmer safety
and prevent harmful advice.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, ClassVar

from pydantic import BaseModel, Field


class SafetyLevel(str, Enum):
    """
    Safety classification levels for queries and responses.

    Levels determine the confidence threshold and approval requirements.
    """

    GENERAL = "general"  # General advisory, low risk
    PEST_TREATMENT = "pest_treatment"  # Pest/disease treatment recommendations
    CHEMICAL_DOSAGE = "chemical_dosage"  # Chemical/pesticide dosage advice (highest risk)
    LEGAL_SCHEME = "legal_scheme"  # Government scheme or legal advice
    WEATHER_ACTION = "weather_action"  # Weather-sensitive actions
    HEALTH_CLAIM = "health_claim"  # Human/animal health claims


# Minimum confidence thresholds by safety level
SAFETY_CONFIDENCE_THRESHOLDS: dict[SafetyLevel, float] = {
    SafetyLevel.GENERAL: 0.70,
    SafetyLevel.PEST_TREATMENT: 0.85,
    SafetyLevel.CHEMICAL_DOSAGE: 0.95,
    SafetyLevel.LEGAL_SCHEME: 0.90,
    SafetyLevel.WEATHER_ACTION: 0.85,
    SafetyLevel.HEALTH_CLAIM: 0.90,
}


class SafetyPolicy(BaseModel):
    """
    Safety policy defining what is allowed/blocked.

    Policies are evaluated before any response is sent to the farmer.
    """

    allow_chemical_advice: bool = Field(
        default=False, description="Whether chemical advice is allowed"
    )
    require_citation_for_dosage: bool = Field(
        default=True, description="Require citations for all dosage advice"
    )
    block_banned_chemicals: bool = Field(
        default=True, description="Block advice about banned chemicals"
    )
    block_human_health_claims: bool = Field(
        default=True, description="Block unverified human health claims"
    )
    block_veterinary_claims: bool = Field(
        default=True, description="Block unverified veterinary claims"
    )
    require_disclaimer_for_treatment: bool = Field(
        default=True, description="Require disclaimers for treatment advice"
    )
    max_confidence_for_fallback: float = Field(
        default=0.50, description="Max confidence to trigger fallback instead of guess"
    )
    blocked_keywords: list[str] = Field(
        default_factory=list, description="Keywords that trigger immediate block"
    )
    banned_chemicals: list[str] = Field(
        default_factory=list, description="List of banned chemical names"
    )

    class Config:
        json_schema_extra: ClassVar[dict[str, Any]] = {
            "example": {
                "allow_chemical_advice": True,
                "require_citation_for_dosage": True,
                "block_banned_chemicals": True,
                "blocked_keywords": ["poison", "suicide"],
                "banned_chemicals": ["DDT", "Lindane", "Endosulfan"],
            }
        }


class SafetyCheckResult(BaseModel):
    """
    Result of a safety check on a query or response.

    Every query and response must pass safety checks before proceeding.
    """

    passed: bool = Field(..., description="Whether the safety check passed")
    safety_level: SafetyLevel = Field(..., description="Detected safety level of the content")
    confidence_threshold: float = Field(
        ..., description="Required confidence threshold for this safety level"
    )
    flags: list[str] = Field(default_factory=list, description="List of safety flags raised")
    blocked_reason: str | None = Field(None, description="Reason for blocking if failed")
    requires_human_review: bool = Field(
        default=False, description="Whether human review is required"
    )
    suggested_action: str = Field(
        default="proceed",
        description="Suggested action: proceed, fallback, block, review",
    )

    class Config:
        json_schema_extra: ClassVar[dict[str, Any]] = {
            "example": {
                "passed": True,
                "safety_level": "pest_treatment",
                "confidence_threshold": 0.85,
                "flags": ["chemical_mentioned"],
                "requires_human_review": False,
                "suggested_action": "proceed",
            }
        }

    @property
    def should_block(self) -> bool:
        """Check if content should be blocked."""
        return not self.passed or self.suggested_action == "block"

    @property
    def should_fallback(self) -> bool:
        """Check if fallback mechanism should be used."""
        return self.suggested_action == "fallback"

    @property
    def should_review(self) -> bool:
        """Check if human review is required."""
        return self.requires_human_review or self.suggested_action == "review"


def get_safety_level_for_query(query_text: str) -> SafetyLevel:
    """
    Determine safety level based on query content.

    This is a simple heuristic; production should use ML classifier.
    """
    query_lower = query_text.lower()

    # Chemical dosage indicators (highest risk)
    chemical_keywords = [
        "dosage",
        "dose",
        "ml per liter",
        "gram per acre",
        "spray concentration",
        "mixing ratio",
    ]
    if any(kw in query_lower for kw in chemical_keywords):
        return SafetyLevel.CHEMICAL_DOSAGE

    # Treatment indicators
    treatment_keywords = [
        "treatment",
        "control",
        "pesticide",
        "insecticide",
        "fungicide",
        "cure",
        "नियंत्रण",
        "फवारणी",
    ]
    if any(kw in query_lower for kw in treatment_keywords):
        return SafetyLevel.PEST_TREATMENT

    # Legal/scheme indicators
    legal_keywords = [
        "scheme",
        "subsidy",
        "loan",
        "compensation",
        "eligibility",
        "योजना",
        "अनुदान",
    ]
    if any(kw in query_lower for kw in legal_keywords):
        return SafetyLevel.LEGAL_SCHEME

    # Weather action indicators
    weather_keywords = [
        "when to sow",
        "when to harvest",
        "rain forecast",
        "weather warning",
        "पेरव्हा कधी",
        "हवामान",
    ]
    if any(kw in query_lower for kw in weather_keywords):
        return SafetyLevel.WEATHER_ACTION

    # Health claim indicators
    health_keywords = [
        "poisonous",
        "edible",
        "toxic",
        "safe to eat",
        "health benefit",
    ]
    if any(kw in query_lower for kw in health_keywords):
        return SafetyLevel.HEALTH_CLAIM

    return SafetyLevel.GENERAL
