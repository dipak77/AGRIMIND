"""Model manifest schemas for immutable model versioning."""

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class ModelManifest(BaseModel):
    """Immutable manifest for a trained model.

    Every model must reference its tokenizer and dataset manifests to ensure
    reproducibility. Models cannot be deployed without passing eval gates.
    """

    model_id: str = Field(..., description="Unique model identifier")
    base_model: str = Field(..., description="Base model used (e.g., Qwen2.5-7B)")
    version: str = Field(..., description="Semantic version of the model")

    # References to immutable artifacts
    tokenizer_manifest_id: str = Field(..., description="Reference to tokenizer manifest")
    dataset_manifest_id: str = Field(
        ..., description="Reference to dataset manifest used for training"
    )

    # Training configuration
    training_config: str = Field(
        ..., description="Training configuration identifier (e.g., lora_r16_alpha32)"
    )
    training_started_at: datetime = Field(..., description="When training started")
    training_completed_at: datetime = Field(..., description="When training completed")

    # Evaluation scores (must pass thresholds before deployment)
    eval_score: dict[str, float] = Field(
        ..., description="Evaluation scores (faithfulness, safety, relevance, etc.)"
    )
    eval_passed: bool = Field(False, description="Whether the model passed all evaluation gates")
    eval_timestamp: datetime | None = Field(None, description="When evaluation was completed")

    # Safety scores
    safety_score: float = Field(..., ge=0.0, le=1.0, description="Safety evaluation score (0-1)")
    hallucination_rate: float = Field(
        ..., ge=0.0, le=1.0, description="Hallucination rate on golden set"
    )

    # Language performance
    language_scores: dict[str, float] = Field(
        default_factory=dict,
        description="Performance by language (en, hi, mr)",
    )

    # Artifact location
    artifact_path: str = Field(..., description="Path to model artifacts in object storage")
    artifact_checksum: str = Field(..., description="SHA-256 checksum of model artifacts")

    # Export formats
    onnx_export_path: str | None = Field(
        None, description="Path to ONNX export for edge deployment"
    )
    quantized: bool = Field(False, description="Whether model is quantized")
    quantization_type: str | None = Field(None, description="Quantization type (INT4, INT8, etc.)")

    # Deployment status
    deployed: bool = Field(False, description="Whether model is deployed")
    deployment_environments: list[str] = Field(
        default_factory=list, description="Environments where model is deployed"
    )
    canary_percentage: float | None = Field(
        None, description="If in canary, percentage of traffic (0-100)"
    )

    # Metadata
    description: str = Field("", description="Model description")
    tags: list[str] = Field(default_factory=list, description="Model tags")
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Manifest creation timestamp"
    )
    frozen: bool = Field(False, description="If true, manifest cannot be modified")

    model_config = {"frozen": True}

    def mark_eval_passed(self, scores: dict[str, float]) -> "ModelManifest":
        """Mark evaluation as passed with given scores."""
        return self.model_copy(
            update={
                "eval_score": scores,
                "eval_passed": True,
                "eval_timestamp": datetime.now(UTC),
            }
        )

    def mark_deployed(
        self, environment: str, canary_percentage: float | None = None
    ) -> "ModelManifest":
        """Mark model as deployed to an environment."""
        envs = self.deployment_environments.copy()
        if environment not in envs:
            envs.append(environment)
        return self.model_copy(
            update={
                "deployed": True,
                "deployment_environments": envs,
                "canary_percentage": canary_percentage,
            }
        )
