"""Checkpoint loader and state restoration helper (P0.3)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Tuple

from foundation_model.pretraining.checkpoint import CheckpointState


def verify_and_load_checkpoint(checkpoint_dir: str | Path) -> Tuple[CheckpointState, Path]:
    """
    Validate checkpoint directory completeness and return restored CheckpointState.
    Fails loud if dataset/tokenizer/model manifests are missing or if scratch contract is violated.
    """
    path = Path(checkpoint_dir)
    state = CheckpointState.load(path)
    state.assert_complete_for_resume()
    return state, path
