"""Model Registry Client for managing model lifecycle."""
from typing import Optional, List
from pathlib import Path
import json
from .schemas import ModelManifest


class ModelRegistryClient:
    """Client for interacting with the model registry."""
    
    def __init__(self, registry_path: str):
        self.registry_path = Path(registry_path)
        self._cache = {}
    
    def get_manifest(self, model_id: str) -> ModelManifest:
        """Get model manifest by ID."""
        if model_id in self._cache:
            return self._cache[model_id]
        
        manifest_path = self.registry_path / f"{model_id}.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Model manifest not found: {model_id}")
        
        with open(manifest_path) as f:
            data = json.load(f)
        
        manifest = ModelManifest(**data)
        self._cache[model_id] = manifest
        return manifest
    
    def list_models(self, status: Optional[str] = None) -> List[ModelManifest]:
        """List all models, optionally filtered by status."""
        manifests = []
        for path in self.registry_path.glob("*.json"):
            with open(path) as f:
                data = json.load(f)
            manifest = ModelManifest(**data)
            if status is None or manifest.status == status:
                manifests.append(manifest)
        return manifests
    
    def register_model(self, manifest: ModelManifest) -> None:
        """Register a new model manifest."""
        if not manifest.is_frozen:
            raise ValueError("Only frozen models can be registered")
        
        manifest_path = self.registry_path / f"{manifest.model_id}.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(manifest_path, 'w') as f:
            json.dump(manifest.model_dump(), f, indent=2, default=str)
    
    def promote_model(self, model_id: str, new_status: str) -> ModelManifest:
        """Promote model to new status (requires manual intervention in real system)."""
        manifest = self.get_manifest(model_id)
        if not manifest.can_promote() and new_status == "production":
            raise ValueError(f"Model {model_id} does not meet promotion criteria")
        
        # In real system, this would create a new manifest version
        # For now, just validate
        return manifest
