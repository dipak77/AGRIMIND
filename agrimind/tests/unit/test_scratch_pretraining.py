"""Unit tests for Scratch Pretraining Engine & Checkpointing (P0.3)."""

import math
import tempfile
from pathlib import Path

import pytest

from foundation_model.architecture.config import load_config
from foundation_model.pretraining.checkpoint import CheckpointState, assert_scratch_manifest
from foundation_model.pretraining.resume import verify_and_load_checkpoint
from foundation_model.pretraining.scheduler import CosineWarmupScheduler
from foundation_model.pretraining.trainer import ScratchPretrainer


def test_cosine_warmup_scheduler() -> None:
    sched = CosineWarmupScheduler(base_lr=1e-3, min_lr=1e-4, warmup_steps=10, max_steps=100)
    assert sched.get_lr(0) == 0.0
    assert sched.get_lr(5) == 5e-4
    assert sched.get_lr(10) == 1e-3
    assert sched.get_lr(100) == 1e-4


def test_scratch_manifest_fail_loud() -> None:
    manifest_bad = {"training_mode": "scratch", "base_checkpoint": "meta-llama/Llama-2-7b"}
    with pytest.raises(ValueError, match="scratch training must have base_checkpoint=null"):
        assert_scratch_manifest(manifest_bad)

    manifest_good = {"training_mode": "scratch", "base_checkpoint": None}
    assert_scratch_manifest(manifest_good)  # should not raise


def test_scratch_pretraining_loop_and_checkpoint_resume() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = load_config("configs/models/krishimini_20m.yaml")
        trainer = ScratchPretrainer(
            config=cfg,
            dataset_manifest_id="ds-test-v1",
            tokenizer_manifest_id="tok-test-16k",
            output_dir=tmpdir,
        )

        def mock_step_fn(step: int, lr: float) -> float:
            return round(8.0 * math.exp(-step / 20.0) + 1.5, 4)

        result = trainer.run_training_loop(mock_step_fn, max_steps=50, tokens_per_step=512)

        assert result["global_step"] == 50
        assert result["tokens_seen"] == 50 * 512
        assert result["final_loss"] < result["initial_loss"]

        # Restore from final checkpoint
        ckpt_dir = Path(result["checkpoint_dir"])
        state, path = verify_and_load_checkpoint(ckpt_dir)
        assert state.global_step == 50
        assert state.tokens_seen == 50 * 512
        assert state.dataset_manifest_id == "ds-test-v1"
        assert state.tokenizer_manifest_id == "tok-test-16k"
        assert state.training_mode == "scratch"
        assert state.base_checkpoint is None
