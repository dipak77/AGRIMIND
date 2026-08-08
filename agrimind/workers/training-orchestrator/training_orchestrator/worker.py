"""Training orchestrator — manifest validation stub (no real GPU training)."""

from __future__ import annotations

from datetime import datetime, timezone

import structlog

logger = structlog.get_logger()


def train_job(dataset_manifest_id: str) -> dict:
    """
    Placeholder training entrypoint.

    Real path: validate manifests -> LoRA/QLoRA -> eval gate -> registry.
    """
    logger.info("train_job_start", dataset_manifest_id=dataset_manifest_id)
    model = {
        "model_id": "agrimind-7b-sim-v0.1.0",
        "dataset_manifest_id": dataset_manifest_id,
        "status": "simulated_complete",
        "eval_score": {"faithfulness": 0.0, "note": "not evaluated — no training run"},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    logger.info("train_job_end", model_id=model["model_id"])
    return model


if __name__ == "__main__":
    print(train_job("ds-local-dev-v1"))
