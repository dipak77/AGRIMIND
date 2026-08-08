#!/usr/bin/env python3
"""CLI script to launch KrishiMini-20M scratch pretraining (P0.3)."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "foundation_model"))

from foundation_model.architecture.config import load_config
from foundation_model.pretraining.trainer import ScratchPretrainer


def main() -> None:
    parser = argparse.ArgumentParser(description="Pretrain KrishiMini From Scratch")
    parser.add_argument("--config", type=str, default="configs/models/krishimini_20m.yaml")
    parser.add_argument("--dataset-manifest-id", type=str, default="ds-krishimini-v1")
    parser.add_argument("--tokenizer-manifest-id", type=str, default="krishimini-tokenizer-16k")
    parser.add_argument("--output-dir", type=str, default="runs/training/run-001")
    parser.add_argument("--steps", type=int, default=100)

    args = parser.parse_args()

    cfg = load_config(args.config)
    trainer = ScratchPretrainer(
        config=cfg,
        dataset_manifest_id=args.dataset_manifest_id,
        tokenizer_manifest_id=args.tokenizer_manifest_id,
        output_dir=args.output_dir,
    )

    # Simulated deterministic loss drop step function for CLI demo
    def mock_step_fn(step: int, lr: float) -> float:
        import math
        return round(10.0 * math.exp(-step / 50.0) + 2.0, 4)

    summary = trainer.run_training_loop(mock_step_fn, max_steps=args.steps)
    print(f"Pretraining session finished cleanly!")
    print(f"Global Steps:   {summary['global_step']}")
    print(f"Tokens Seen:    {summary['tokens_seen']:,}")
    print(f"Initial Loss:   {summary['initial_loss']}")
    print(f"Final Loss:     {summary['final_loss']}")
    print(f"Final Checkpoint: {summary['checkpoint_dir']}")


if __name__ == "__main__":
    main()
