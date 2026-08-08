"""Complete checkpoint state contract for resume (P1.19 skeleton + P0.3 gates)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
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
    # RNG / optimizer blobs stored as paths or base64 by trainer implementation
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


def assert_scratch_manifest(manifest: dict[str, Any]) -> None:
    """CI gate: scratch run must not reference a pretrained checkpoint."""
    mode = str(manifest.get("training_mode") or "").lower()
    base = manifest.get("base_checkpoint")
    if mode == "scratch" and base not in (None, "", "null"):
        raise ValueError(
            f"CI fail: scratch training must have base_checkpoint=null (got {base!r})"
        )
