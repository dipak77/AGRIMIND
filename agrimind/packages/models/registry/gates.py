"""Fail-loud model/tokenizer gates for training serve and promotion (D2/D3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from registry.schemas import EvalScores, ModelManifest


# Production promotion thresholds (plan: eval-gated deployment)
MIN_FAITHFULNESS = 0.90
MIN_SAFETY = 1.0
MIN_RELEVANCE = 0.70
SERVABLE_STATUSES = frozenset({"canary", "production", "staging"})  # staging ok for local sim


class GateError(ValueError):
    """Raised when a model/tokenizer gate fails (fail loud)."""


@dataclass
class PromotionDecision:
    allowed: bool
    model_id: str
    reasons: list[str]
    eval_score: dict[str, Any]


def assert_tokenizer_matches_model(
    *,
    model: ModelManifest,
    tokenizer_id: str,
    tokenizer_checksum: str | None = None,
    expected_checksum: str | None = None,
) -> None:
    """D2: tokenizer_manifest_id must match; optional checksum fail-loud."""
    if model.tokenizer_manifest_id != tokenizer_id:
        raise GateError(
            f"Tokenizer mismatch: model {model.model_id} requires "
            f"{model.tokenizer_manifest_id}, got {tokenizer_id}"
        )
    if expected_checksum and tokenizer_checksum and expected_checksum != tokenizer_checksum:
        raise GateError(
            f"Tokenizer checksum mismatch for {tokenizer_id}: "
            f"expected {expected_checksum}, got {tokenizer_checksum}"
        )


def assert_dataset_matches_model(*, model: ModelManifest, dataset_manifest_id: str) -> None:
    """D2: dataset lineage must match training manifest."""
    if model.dataset_manifest_id != dataset_manifest_id:
        raise GateError(
            f"Dataset mismatch: model {model.model_id} trained on "
            f"{model.dataset_manifest_id}, got {dataset_manifest_id}"
        )


def evaluate_promotion(
    manifest: ModelManifest,
    *,
    min_faithfulness: float = MIN_FAITHFULNESS,
    min_safety: float = MIN_SAFETY,
    min_relevance: float | None = MIN_RELEVANCE,
    target_status: str = "production",
) -> PromotionDecision:
    """D3: score-threshold gate for promotions."""
    reasons: list[str] = []
    scores = manifest.eval_score
    if scores.faithfulness < min_faithfulness:
        reasons.append(
            f"faithfulness {scores.faithfulness:.3f} < {min_faithfulness:.3f}"
        )
    if scores.safety < min_safety:
        reasons.append(f"safety {scores.safety:.3f} < {min_safety:.3f}")
    if min_relevance is not None and scores.relevance is not None:
        if scores.relevance < min_relevance:
            reasons.append(f"relevance {scores.relevance:.3f} < {min_relevance:.3f}")
    if target_status == "production" and manifest.status not in ("staging", "canary"):
        reasons.append(f"invalid source status for production: {manifest.status}")
    if not manifest.is_frozen:
        reasons.append("model manifest is not frozen")

    return PromotionDecision(
        allowed=len(reasons) == 0,
        model_id=manifest.model_id,
        reasons=reasons,
        eval_score=scores.model_dump(),
    )


def assert_can_promote(manifest: ModelManifest, **kwargs: Any) -> None:
    decision = evaluate_promotion(manifest, **kwargs)
    if not decision.allowed:
        raise GateError(
            f"Promotion blocked for {manifest.model_id}: " + "; ".join(decision.reasons)
        )


def assert_model_servable(registry: Any, model_id: str) -> ModelManifest:
    """Fail loud if model not registered or not in a servable status."""
    try:
        manifest: ModelManifest = registry.get_manifest(model_id)
    except FileNotFoundError as exc:
        raise GateError(f"Unknown model_id (not in registry): {model_id}") from exc
    if manifest.status not in SERVABLE_STATUSES:
        raise GateError(
            f"Model {model_id} status={manifest.status} is not servable "
            f"(allowed: {sorted(SERVABLE_STATUSES)})"
        )
    if manifest.status == "deprecated":
        raise GateError(f"Model {model_id} is deprecated")
    return manifest


def scores_pass_thresholds(
    scores: EvalScores,
    *,
    min_faithfulness: float = MIN_FAITHFULNESS,
    min_safety: float = MIN_SAFETY,
) -> bool:
    return scores.faithfulness >= min_faithfulness and scores.safety >= min_safety
