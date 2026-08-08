"""Default model manifests for local/dev registry seed."""

from __future__ import annotations

from registry.schemas import EvalScores, ModelManifest


def default_manifests() -> list[ModelManifest]:
    good = ModelManifest(
        model_id="agrimind-7b-sim-v0.1.0",
        base_model="Qwen2.5-7B",
        tokenizer_manifest_id="agrimind-tokenizer-v1",
        dataset_manifest_id="ds-2026-seed-v1",
        training_config="lora_r16_sim",
        eval_score=EvalScores(faithfulness=0.96, safety=1.0, relevance=0.90),
        artifact_path="s3://agrimind-models/7b/sim-v0.1.0",
        model_type="cloud",
        param_count="7B",
        status="staging",
        is_frozen=True,
    )
    edge = ModelManifest(
        model_id="agrimind-18m-sim-v0.1.0",
        base_model="agrimind-18m",
        tokenizer_manifest_id="agrimind-tokenizer-v1",
        dataset_manifest_id="ds-2026-seed-v1",
        training_config="edge_int8_sim",
        eval_score=EvalScores(faithfulness=0.91, safety=1.0, relevance=0.85),
        artifact_path="s3://agrimind-models/18m/sim-v0.1.0",
        model_type="edge",
        param_count="18M",
        status="staging",
        is_frozen=True,
    )
    # Intentionally bad model for gate tests / blocked promotion
    bad = ModelManifest(
        model_id="agrimind-7b-bad-v0.0.1",
        base_model="Qwen2.5-7B",
        tokenizer_manifest_id="agrimind-tokenizer-v1",
        dataset_manifest_id="ds-2026-seed-v1",
        training_config="broken",
        eval_score=EvalScores(faithfulness=0.40, safety=0.50, relevance=0.30),
        artifact_path="s3://agrimind-models/7b/bad",
        model_type="cloud",
        status="staging",
        is_frozen=True,
    )
    return [good, edge, bad]
