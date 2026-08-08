"""Agriculture relevance scoring (lightweight keyword classifier)."""

from __future__ import annotations

from dataclasses import dataclass

AGRI_KEYWORDS = {
    "crop",
    "soil",
    "pest",
    "farm",
    "farmer",
    "fertilizer",
    "irrigation",
    "cotton",
    "wheat",
    "rice",
    "bollworm",
    "ipm",
    "pesticide",
    "harvest",
    "sowing",
    "कृषि",
    "शेत",
    "पिक",
    "खत",
    "कीड",
    "फसल",
    "मिट्टी",
    "खेती",
}


@dataclass
class RelevanceResult:
    relevant: bool
    score: float
    matched: list[str]


class AgricultureRelevanceFilter:
    def __init__(self, threshold: float = 0.5) -> None:
        self.threshold = threshold

    def score(self, text: str) -> RelevanceResult:
        lower = text.lower()
        matched = [k for k in AGRI_KEYWORDS if k in lower]
        # simple score: cap at 1.0
        raw = len(matched) / 5.0
        score = min(1.0, max(0.0, raw if matched else 0.1))
        # boost if multiple signals
        if len(matched) >= 2:
            score = max(score, 0.7)
        if len(matched) >= 4:
            score = max(score, 0.9)
        return RelevanceResult(
            relevant=score >= self.threshold,
            score=score,
            matched=matched[:10],
        )
