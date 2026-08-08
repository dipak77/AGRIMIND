"""Fail-loud architecture validation against parameter budget."""

from __future__ import annotations

from dataclasses import dataclass

from foundation_model.architecture.config import KrishiMiniConfig
from foundation_model.architecture.param_count import ParamBreakdown, count_from_config


@dataclass
class ArchitectureValidation:
    ok: bool
    breakdown: ParamBreakdown
    target: int
    budget_min: int
    budget_max: int
    errors: list[str]
    warnings: list[str]

    def raise_if_invalid(self) -> None:
        if not self.ok:
            raise ValueError("; ".join(self.errors))


def validate_architecture(cfg: KrishiMiniConfig) -> ArchitectureValidation:
    errors: list[str] = []
    warnings: list[str] = []

    try:
        cfg.assert_scratch_contract()
    except ValueError as exc:
        errors.append(str(exc))

    arch = cfg.architecture
    if arch.hidden_size != arch.attention_heads * arch.head_dim:
        errors.append(
            f"hidden_size ({arch.hidden_size}) != attention_heads*head_dim "
            f"({arch.attention_heads}*{arch.head_dim}={arch.attention_heads * arch.head_dim})"
        )
    if arch.vocab_size_mismatch if False else False:  # placeholder
        pass

    # 64K vocab warning for small models
    if cfg.tokenizer.vocab_size >= 64000 and cfg.target_parameters <= 25_000_000:
        warnings.append(
            f"vocab_size={cfg.tokenizer.vocab_size} is large for "
            f"~{cfg.target_parameters // 1_000_000}M model (embedding matrix dominates)"
        )
    if cfg.tokenizer.vocab_size not in (cfg.tokenizer.candidates or [cfg.tokenizer.vocab_size]):
        warnings.append(
            f"vocab_size {cfg.tokenizer.vocab_size} not in candidates {cfg.tokenizer.candidates}"
        )

    breakdown = count_from_config(cfg)
    bmin = cfg.parameter_budget.min
    bmax = cfg.parameter_budget.max
    if not (bmin <= breakdown.total_parameters <= bmax):
        errors.append(
            f"total_parameters={breakdown.total_parameters} outside budget "
            f"[{bmin}, {bmax}] (target={cfg.target_parameters})"
        )

    # embedding share should not exceed ~40% for healthy small models
    emb_share = breakdown.embedding_parameters / max(breakdown.total_parameters, 1)
    if emb_share > 0.45:
        warnings.append(
            f"embedding params are {emb_share:.1%} of total — consider smaller vocab"
        )

    return ArchitectureValidation(
        ok=len(errors) == 0,
        breakdown=breakdown,
        target=cfg.target_parameters,
        budget_min=bmin,
        budget_max=bmax,
        errors=errors,
        warnings=warnings,
    )
