"""Quality scoring for curated records (Phase 2 stage 9)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class QualityResult:
    score: float
    factors: dict[str, float]


def score_quality(
    *,
    text: str,
    relevance: float,
    language: str,
    pii_redacted: bool,
    has_provenance: bool,
    toxicity_score: float = 1.0,
) -> QualityResult:
    factors: dict[str, float] = {}
    # length heuristic
    n = len(text or "")
    if n < 40:
        factors["length"] = 0.3
    elif n < 200:
        factors["length"] = 0.6
    elif n < 20000:
        factors["length"] = 0.9
    else:
        factors["length"] = 0.7  # very long may be noisy
    factors["relevance"] = max(0.0, min(1.0, relevance))
    factors["language"] = 0.95 if language in ("en", "hi", "mr") else 0.5
    factors["toxicity"] = toxicity_score
    factors["provenance"] = 1.0 if has_provenance else 0.4
    factors["pii_handling"] = 0.9 if pii_redacted else 0.85
    # weighted average
    weights = {
        "length": 0.15,
        "relevance": 0.35,
        "language": 0.15,
        "toxicity": 0.2,
        "provenance": 0.1,
        "pii_handling": 0.05,
    }
    score = sum(factors[k] * weights[k] for k in weights)
    return QualityResult(score=round(min(1.0, max(0.0, score)), 4), factors=factors)
