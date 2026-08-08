"""Unit tests for KrishiMini-20M architecture contract & parameter counting (P0.2/P0.4)."""

import pytest

from foundation_model.architecture.config import ArchitectureCfg, KrishiMiniConfig, load_config
from foundation_model.architecture.model import HAS_TORCH, KrishiMiniTransformer, build_scratch_model_spec
from foundation_model.architecture.param_count import count_from_config, count_parameters
from foundation_model.architecture.validation import validate_architecture


def test_krishimini_20m_config_load() -> None:
    cfg = load_config("configs/models/krishimini_20m.yaml")
    assert cfg.model_family == "krishimini"
    assert cfg.target_parameters == 20_000_000
    assert cfg.tokenizer.vocab_size == 16000
    assert cfg.training.mode == "scratch"
    assert cfg.training.base_checkpoint is None


def test_exact_parameter_calculation() -> None:
    cfg = load_config("configs/models/krishimini_20m.yaml")
    breakdown = count_from_config(cfg)
    
    # 21,880,704 total parameters
    assert 18_000_000 <= breakdown.total_parameters <= 22_000_000
    assert breakdown.embedding_parameters == 16000 * 384
    assert breakdown.lm_head_parameters == 0  # tied embeddings
    assert breakdown.layers == 10
    assert breakdown.hidden_size == 384


def test_scratch_contract_fail_loud() -> None:
    cfg = load_config("configs/models/krishimini_20m.yaml")
    cfg.training.base_checkpoint = "some-pretrained-ckpt"
    
    val = validate_architecture(cfg)
    assert not val.ok
    assert any("scratch training forbids base_checkpoint" in err for err in val.errors)


def test_scratch_spec_builder() -> None:
    cfg = load_config("configs/models/krishimini_20m.yaml")
    spec = build_scratch_model_spec(cfg)
    assert spec.training_mode == "scratch"
    fields = spec.to_manifest_fields()
    assert fields["target_parameters"] == 20_000_000
    assert fields["vocab_size"] == 16000


def test_pytorch_model_instantiation_and_forward() -> None:
    if not HAS_TORCH:
        pytest.skip("PyTorch not installed in test environment")
    import torch

    cfg = load_config("configs/models/krishimini_20m.yaml")
    model = KrishiMiniTransformer(cfg)
    
    # Verify PyTorch model parameter count matches analytical calculation exactly
    total_torch_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    analytical_breakdown = count_from_config(cfg)
    assert total_torch_params == analytical_breakdown.total_parameters

    # Forward pass smoke test
    input_ids = torch.randint(0, 16000, (2, 32))
    labels = input_ids.clone()
    out = model(input_ids, labels=labels)
    
    assert out["logits"].shape == (2, 32, 16000)
    assert out["loss"] is not None
    assert not torch.isnan(out["loss"])
