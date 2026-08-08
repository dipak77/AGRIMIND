"""Scratch pretraining trainer implementation with checkpointing & laptop controller (P0.3)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List

from foundation_model.architecture.config import KrishiMiniConfig
from foundation_model.pretraining.checkpoint import CheckpointState, assert_scratch_manifest
from foundation_model.pretraining.laptop_controller import LaptopTrainingController
from foundation_model.pretraining.scheduler import CosineWarmupScheduler


class ScratchPretrainer:
    """Pretrainer enforcing scratch training initialization contract."""

    def __init__(
        self,
        config: KrishiMiniConfig,
        dataset_manifest_id: str,
        tokenizer_manifest_id: str,
        output_dir: str | Path,
    ) -> None:
        self.config = config
        self.dataset_manifest_id = dataset_manifest_id
        self.tokenizer_manifest_id = tokenizer_manifest_id
        self.output_dir = Path(output_dir)

        # Enforce scratch contract (base_checkpoint must be null)
        self.config.assert_scratch_contract()
        assert_scratch_manifest({
            "training_mode": self.config.training.mode,
            "base_checkpoint": self.config.training.base_checkpoint,
        })

        self.scheduler = CosineWarmupScheduler(
            base_lr=3e-4,
            min_lr=3e-5,
            warmup_steps=100,
            max_steps=1000,
        )
        self.controller = LaptopTrainingController(
            max_session_minutes=self.config.training.max_session_minutes,
            checkpoint_interval_minutes=self.config.training.checkpoint_interval_minutes,
            checkpoint_interval_tokens=self.config.training.checkpoint_interval_tokens,
        )

        self.global_step = 0
        self.tokens_seen = 0
        self.loss_history: List[float] = []

    def save_checkpoint(self, tag: str | None = None) -> CheckpointState:
        step_tag = tag or f"step-{self.global_step}"
        ckpt_dir = self.output_dir / "checkpoints" / step_tag
        state = CheckpointState(
            global_step=self.global_step,
            tokens_seen=self.tokens_seen,
            dataset_manifest_id=self.dataset_manifest_id,
            tokenizer_manifest_id=self.tokenizer_manifest_id,
            model_config_id=self.config.model_id,
            training_mode="scratch",
            base_checkpoint=None,
        )
        state.save(ckpt_dir)
        return state

    def run_training_loop(
        self,
        step_fn: Callable[[int, float], float],
        max_steps: int = 100,
        tokens_per_step: int = 1024,
    ) -> Dict[str, Any]:
        """
        Execute scratch pretraining step loop.
        step_fn(step, lr) returns the scalar loss for that step.
        """
        while self.global_step < max_steps and not self.controller.should_stop():
            lr = self.scheduler.get_lr(self.global_step)
            loss = step_fn(self.global_step, lr)
            
            self.global_step += 1
            self.tokens_seen += tokens_per_step
            self.loss_history.append(loss)
            self.controller.note_tokens(tokens_per_step)

            if self.controller.should_checkpoint():
                self.save_checkpoint()
                self.controller.mark_checkpoint_done()

        final_ckpt = self.save_checkpoint(tag="final")
        return {
            "global_step": self.global_step,
            "tokens_seen": self.tokens_seen,
            "initial_loss": self.loss_history[0] if self.loss_history else 0.0,
            "final_loss": self.loss_history[-1] if self.loss_history else 0.0,
            "checkpoint_dir": str(self.output_dir / "checkpoints" / "final"),
        }
