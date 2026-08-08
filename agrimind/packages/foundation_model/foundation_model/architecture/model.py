"""Model factory interface (weights initialized from scratch — no pretrained load)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from foundation_model.architecture.config import KrishiMiniConfig
from foundation_model.architecture.validation import validate_architecture


@dataclass
class ScratchModelSpec:
    """Spec ready for torch/jax implementation; no weights bundled here."""

    config: KrishiMiniConfig
    training_mode: str
    base_checkpoint: None
    param_total: int
    init: str = "from_scratch"

    def to_manifest_fields(self) -> dict[str, Any]:
        return {
            "model_id": self.config.model_id,
            "model_family": self.config.model_family,
            "training_mode": "scratch",
            "base_checkpoint": None,
            "target_parameters": self.config.target_parameters,
            "total_parameters": self.param_total,
            "vocab_size": self.config.tokenizer.vocab_size,
            "architecture": self.config.architecture.model_dump(),
        }


def build_scratch_model_spec(cfg: KrishiMiniConfig | None = None) -> ScratchModelSpec:
    """Validate config and return a scratch-init model specification."""
    from foundation_model.architecture.config import load_config

    cfg = cfg or load_config()
    result = validate_architecture(cfg)
    result.raise_if_invalid()
    return ScratchModelSpec(
        config=cfg,
        training_mode="scratch",
        base_checkpoint=None,
        param_total=result.breakdown.total_parameters,
    )
