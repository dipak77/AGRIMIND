"""Model registry client — filesystem manifests + fail-loud promotion (D2/D3)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from registry.gates import GateError, assert_can_promote, evaluate_promotion
from registry.schemas import ModelManifest


class ModelRegistryClient:
    """Client for interacting with the model registry (local directory of JSON manifests)."""

    def __init__(self, registry_path: str | Path) -> None:
        self.registry_path = Path(registry_path)
        self.registry_path.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, ModelManifest] = {}

    def get_manifest(self, model_id: str) -> ModelManifest:
        if model_id in self._cache:
            return self._cache[model_id]
        manifest_path = self.registry_path / f"{model_id}.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Model manifest not found: {model_id}")
        with open(manifest_path, encoding="utf-8") as f:
            data = json.load(f)
        manifest = ModelManifest(**data)
        self._cache[model_id] = manifest
        return manifest

    def list_models(self, status: Optional[str] = None) -> List[ModelManifest]:
        manifests: list[ModelManifest] = []
        for path in sorted(self.registry_path.glob("*.json")):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            manifest = ModelManifest(**data)
            if status is None or manifest.status == status:
                manifests.append(manifest)
        return manifests

    def register_model(self, manifest: ModelManifest) -> None:
        if not manifest.is_frozen:
            raise ValueError("Only frozen models can be registered")
        # D2: reject if eval scores missing safety floor for production registration
        if manifest.status == "production":
            assert_can_promote(manifest, target_status="production")
        manifest_path = self.registry_path / f"{manifest.model_id}.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest.model_dump(mode="json"), f, indent=2, default=str)
        self._cache[manifest.model_id] = manifest

    def promote_model(self, model_id: str, new_status: str = "production") -> ModelManifest:
        """
        Promote model after eval gate (D3).
        Writes updated manifest (unfreeze-copy) to registry.
        """
        manifest = self.get_manifest(model_id)
        if new_status == "production":
            decision = evaluate_promotion(manifest, target_status="production")
            if not decision.allowed:
                raise GateError(
                    f"Promotion blocked for {model_id}: " + "; ".join(decision.reasons)
                )
        # ModelManifest may be frozen — use model_copy
        updated = manifest.model_copy(update={"status": new_status})
        # re-register
        path = self.registry_path / f"{model_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(updated.model_dump(mode="json"), f, indent=2, default=str)
        self._cache[model_id] = updated
        return updated

    def ensure_seed_defaults(self) -> list[str]:
        """Register default sim models if registry empty."""
        from registry.seed import default_manifests

        written: list[str] = []
        for m in default_manifests():
            path = self.registry_path / f"{m.model_id}.json"
            if not path.exists():
                self.register_model(m)
                written.append(m.model_id)
        return written
