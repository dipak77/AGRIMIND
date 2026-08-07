"""Model registry schemas and manifests."""
from pydantic import BaseModel, Field
from typing import Dict, Optional, Literal
from datetime import datetime


class EvalScores(BaseModel):
    """Model evaluation scores."""
    faithfulness: float = Field(ge=0.0, le=1.0)
    safety: float = Field(ge=0.0, le=1.0)
    relevance: Optional[float] = None
    language_quality: Optional[Dict[str, float]] = None


class ModelManifest(BaseModel):
    """Immutable model manifest with full lineage."""
    model_id: str
    base_model: str
    tokenizer_manifest_id: str
    dataset_manifest_id: str
    training_config: str
    eval_score: EvalScores
    artifact_path: str  # S3/MinIO path
    model_type: Literal["edge", "cloud"] = "cloud"
    param_count: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_frozen: bool = True
    status: Literal["staging", "canary", "production", "deprecated"] = "staging"
    
    class Config:
        frozen = True
    
    def can_promote(self) -> bool:
        """Check if model meets promotion criteria."""
        return (
            self.eval_score.faithfulness >= 0.95 and
            self.eval_score.safety == 1.0 and
            self.status == "staging"
        )
