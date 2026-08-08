"""Complete checkpoint state contract for resume (P1.19 skeleton + P0.3 gates)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class CheckpointState:
    global_step: int = 0
    tokens_seen: int = 0
    dataset_manifest_id: str = ""
    tokenizer_manifest_id: str = ""
    model_config_id: str = "krishimini-20m"
    current_shard: str = ""
    current_offset: int = 0
    training_mode: str = "scratch"
    base_checkpoint: str | None = None
    git_commit: str | None = None
    hardware_metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    optimizer_state_ref: str | None = None
    scheduler_state_ref: str | None = None
    rng_state_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def assert_complete_for_resume(self) -> None:
        missing = []
        for k in (
            "dataset_manifest_id",
            "tokenizer_manifest_id",
            "model_config_id",
        ):
            if not getattr(self, k):
                missing.append(k)
        if missing:
            raise ValueError(f"checkpoint incomplete for resume: missing {missing}")
        
        # Enforce P0.3 scratch contract gate
        if self.training_mode.lower() == "scratch" and self.base_checkpoint not in (None, "", "null"):
            raise ValueError(
                f"CI fail: scratch training state must have base_checkpoint=null (got {self.base_checkpoint!r})"
            )

    def save(self, checkpoint_dir: str | Path) -> Path:
        self.assert_complete_for_resume()
        p = Path(checkpoint_dir)
        p.mkdir(parents=True, exist_ok=True)
        meta_file = p / "checkpoint_state.json"
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
        return meta_file

    @classmethod
    def load(cls, checkpoint_dir: str | Path) -> CheckpointState:
        p = Path(checkpoint_dir) / "checkpoint_state.json"
        if not p.is_file():
            raise FileNotFoundError(f"Checkpoint state file not found: {p}")
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        state = cls(**data)
        state.assert_complete_for_resume()
        return state


def assert_scratch_manifest(manifest: dict[str, Any]) -> None:
    """CI gate: scratch run must not reference a pretrained checkpoint."""
    mode = str(manifest.get("training_mode") or "").lower()
    base = manifest.get("base_checkpoint")
    if mode == "scratch" and base not in (None, "", "null"):
        raise ValueError(
            f"CI fail: scratch training must have base_checkpoint=null (got {base!r})"
        )
