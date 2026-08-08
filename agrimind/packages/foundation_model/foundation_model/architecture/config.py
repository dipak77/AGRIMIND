"""KrishiMini architecture configuration (YAML-backed)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ArchitectureCfg(BaseModel):
    type: Literal["decoder_only_transformer"] = "decoder_only_transformer"
    layers: int = Field(ge=1, le=64)
    hidden_size: int = Field(ge=64, le=4096)
    attention_heads: int = Field(ge=1, le=64)
    kv_heads: int = Field(ge=1, le=64)
    head_dim: int = Field(ge=16, le=256)
    ffn_hidden_size: int = Field(ge=64, le=16384)
    activation: str = "swiglu"
    normalization: str = "rmsnorm"
    positional_encoding: str = "rope"
    tie_embeddings: bool = True
    bias: bool = False

    @field_validator("kv_heads")
    @classmethod
    def kv_divides_heads(cls, v: int, info: Any) -> int:
        heads = info.data.get("attention_heads")
        if heads is not None and heads % v != 0:
            raise ValueError(f"attention_heads ({heads}) must be divisible by kv_heads ({v})")
        return v


class TokenizerCfg(BaseModel):
    vocab_size: int = Field(default=16000, ge=1000, le=128000)
    candidates: list[int] = Field(default_factory=lambda: [12000, 16000, 24000])
    initial_candidate: int = 16000
    languages: list[str] = Field(default_factory=lambda: ["en", "hi", "mr"])
    normalization: str = "NFKC"


class ParameterBudget(BaseModel):
    min: int = 18_000_000
    max: int = 22_000_000
    note: str = ""


class TrainingCfg(BaseModel):
    mode: Literal["scratch", "continue", "sft", "dpo"] = "scratch"
    base_checkpoint: str | None = None
    context_length: int = 1024
    max_session_minutes: int = 60
    checkpoint_interval_minutes: int = 10
    checkpoint_interval_tokens: int = 1_000_000
    language_mix: dict[str, float] = Field(
        default_factory=lambda: {"hi": 0.35, "mr": 0.35, "en": 0.30}
    )


class KrishiMiniConfig(BaseModel):
    model_family: str = "krishimini"
    model_id: str = "krishimini-20m"
    target_parameters: int = 20_000_000
    parameter_budget: ParameterBudget = Field(default_factory=ParameterBudget)
    architecture: ArchitectureCfg
    tokenizer: TokenizerCfg = Field(default_factory=TokenizerCfg)
    training: TrainingCfg = Field(default_factory=TrainingCfg)

    def assert_scratch_contract(self) -> None:
        """Fail loud if scratch mode references a pretrained checkpoint."""
        if self.training.mode == "scratch" and self.training.base_checkpoint:
            raise ValueError(
                "scratch training forbids base_checkpoint "
                f"(got {self.training.base_checkpoint!r})"
            )


def load_config(path: str | Path | None = None) -> KrishiMiniConfig:
    """Load YAML config; default configs/models/krishimini_20m.yaml."""
    if path is None:
        # try common locations relative to CWD / package
        candidates = [
            Path("configs/models/krishimini_20m.yaml"),
            Path("agrimind/configs/models/krishimini_20m.yaml"),
            Path(__file__).resolve().parents[3] / "configs" / "models" / "krishimini_20m.yaml",
            Path(__file__).resolve().parents[4] / "configs" / "models" / "krishimini_20m.yaml",
        ]
        for c in candidates:
            if c.is_file():
                path = c
                break
        if path is None:
            # pure defaults matching the directive
            return KrishiMiniConfig(
                architecture=ArchitectureCfg(
                    layers=10,
                    hidden_size=384,
                    attention_heads=6,
                    kv_heads=2,
                    head_dim=64,
                    ffn_hidden_size=1024,
                )
            )
    import yaml

    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return KrishiMiniConfig.model_validate(data)
