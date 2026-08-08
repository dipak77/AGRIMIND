#!/usr/bin/env python3
"""CLI utility to calculate exact parameter count for KrishiMini model configs (P0.2/P0.4)."""

import argparse
import json
import sys
from pathlib import Path

# Insert package path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "foundation_model"))

from foundation_model.architecture.config import load_config
from foundation_model.architecture.param_count import count_from_config
from foundation_model.architecture.validation import validate_architecture


def main() -> None:
    parser = argparse.ArgumentParser(description="KrishiMini Model Parameter Count Utility")
    parser.add_argument("--config", type=str, default="configs/models/krishimini_20m.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    breakdown = count_from_config(cfg)
    val = validate_architecture(cfg)

    print(f"=== Model Parameter Breakdown ({cfg.model_id}) ===")
    print(f"Target Parameters:       {cfg.target_parameters:,}")
    print(f"Total Parameters:        {breakdown.total_parameters:,}")
    print(f"Embedding Parameters:    {breakdown.embedding_parameters:,} ({breakdown.embedding_parameters / breakdown.total_parameters:.1%})")
    print(f"Attention Parameters:    {breakdown.attention_parameters:,}")
    print(f"FFN Parameters:          {breakdown.ffn_parameters:,}")
    print(f"Norm Parameters:         {breakdown.norm_parameters:,}")
    print(f"Tied Embeddings:         {breakdown.tied_embeddings}")
    print(f"Budget Valid:            {val.ok}")
    if val.errors:
        print(f"ERRORS: {val.errors}")
    if val.warnings:
        print(f"WARNINGS: {val.warnings}")

    if not val.ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
