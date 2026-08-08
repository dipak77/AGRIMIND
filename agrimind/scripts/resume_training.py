#!/usr/bin/env python3
"""CLI script to resume KrishiMini pretraining from checkpoint (P0.3)."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "foundation_model"))

from foundation_model.pretraining.resume import verify_and_load_checkpoint


def main() -> None:
    parser = argparse.ArgumentParser(description="Resume KrishiMini Pretraining")
    parser.add_argument("--checkpoint-dir", type=str, required=True, help="Path to checkpoint directory")

    args = parser.parse_args()

    state, path = verify_and_load_checkpoint(args.checkpoint_dir)
    print(f"Checkpoint verified and loaded successfully from: {path}")
    print(f"Global Step:           {state.global_step}")
    print(f"Tokens Seen:           {state.tokens_seen:,}")
    print(f"Dataset Manifest ID:   {state.dataset_manifest_id}")
    print(f"Tokenizer Manifest ID: {state.tokenizer_manifest_id}")
    print(f"Training Mode:         {state.training_mode}")
    print(f"Base Checkpoint:       {state.base_checkpoint}")


if __name__ == "__main__":
    main()
