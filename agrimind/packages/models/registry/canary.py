"""Canary deployment + auto-rollback hooks (E3)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from registry.client import ModelRegistryClient
from registry.gates import GateError, evaluate_promotion
from registry.schemas import EvalScores, ModelManifest


@dataclass
class CanaryState:
    production_model_id: str | None = None
    canary_model_id: str | None = None
    canary_traffic_pct: int = 10  # 0-100
    previous_production_model_id: str | None = None
    last_eval: dict[str, Any] = field(default_factory=dict)
    last_action: str = "init"
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CanaryState":
        fields = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in fields})


@dataclass
class RollbackResult:
    rolled_back: bool
    reason: str
    active_production: str | None
    state: dict[str, Any]


class CanaryController:
    """
    Manage canary model pointer + regression-triggered rollback.

    Offline-friendly: state file on disk. Inference service may read canary
    traffic split for routing (optional).
    """

    def __init__(
        self,
        registry: ModelRegistryClient,
        state_path: str | Path = "./data/model-registry/canary_state.json",
        *,
        min_faithfulness: float = 0.90,
        min_safety: float = 1.0,
    ) -> None:
        self.registry = registry
        self.state_path = Path(state_path)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.min_faithfulness = min_faithfulness
        self.min_safety = min_safety
        self.state = self._load()

    def _load(self) -> CanaryState:
        if not self.state_path.exists():
            return CanaryState()
        with self.state_path.open(encoding="utf-8") as f:
            return CanaryState.from_dict(json.load(f))

    def _save(self) -> None:
        self.state.updated_at = datetime.now(timezone.utc).isoformat()
        with self.state_path.open("w", encoding="utf-8") as f:
            json.dump(self.state.to_dict(), f, indent=2)

    def set_production(self, model_id: str) -> CanaryState:
        manifest = self.registry.get_manifest(model_id)
        # promote if needed
        if manifest.status != "production":
            self.registry.promote_model(model_id, "production")
        self.state.previous_production_model_id = self.state.production_model_id
        self.state.production_model_id = model_id
        self.state.last_action = f"set_production:{model_id}"
        self._save()
        return self.state

    def start_canary(self, model_id: str, traffic_pct: int = 10) -> CanaryState:
        if traffic_pct < 0 or traffic_pct > 100:
            raise ValueError("traffic_pct must be 0-100")
        manifest = self.registry.get_manifest(model_id)
        decision = evaluate_promotion(
            manifest,
            min_faithfulness=self.min_faithfulness,
            min_safety=self.min_safety,
            target_status="production",
        )
        if not decision.allowed:
            raise GateError(
                "Canary blocked — model fails eval gate: " + "; ".join(decision.reasons)
            )
        # mark canary in registry
        self.registry.promote_model(model_id, "canary")
        self.state.canary_model_id = model_id
        self.state.canary_traffic_pct = traffic_pct
        self.state.last_action = f"start_canary:{model_id}:{traffic_pct}"
        self.state.last_eval = decision.eval_score
        self._save()
        return self.state

    def evaluate_canary_and_maybe_rollback(
        self,
        canary_scores: EvalScores | dict[str, float],
        *,
        production_scores: EvalScores | dict[str, float] | None = None,
        max_faithfulness_drop: float = 0.05,
    ) -> RollbackResult:
        """
        If canary scores regress vs thresholds (or vs production), auto-rollback.
        """
        if isinstance(canary_scores, dict):
            canary_scores = EvalScores(**canary_scores)
        self.state.last_eval = {
            "canary": canary_scores.model_dump(),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

        reasons: list[str] = []
        if canary_scores.faithfulness < self.min_faithfulness:
            reasons.append(
                f"canary faithfulness {canary_scores.faithfulness} < {self.min_faithfulness}"
            )
        if canary_scores.safety < self.min_safety:
            reasons.append(f"canary safety {canary_scores.safety} < {self.min_safety}")

        if production_scores is not None:
            if isinstance(production_scores, dict):
                production_scores = EvalScores(**production_scores)
            drop = production_scores.faithfulness - canary_scores.faithfulness
            if drop > max_faithfulness_drop:
                reasons.append(
                    f"canary faithfulness drop {drop:.3f} > {max_faithfulness_drop}"
                )

        if reasons:
            return self.rollback(reason="; ".join(reasons))

        self.state.last_action = "canary_eval_pass"
        self._save()
        return RollbackResult(
            rolled_back=False,
            reason="canary_ok",
            active_production=self.state.production_model_id,
            state=self.state.to_dict(),
        )

    def promote_canary_to_production(self) -> CanaryState:
        if not self.state.canary_model_id:
            raise ValueError("no canary model set")
        cid = self.state.canary_model_id
        self.set_production(cid)
        self.state.canary_model_id = None
        self.state.canary_traffic_pct = 0
        self.state.last_action = f"promote_canary:{cid}"
        self._save()
        return self.state

    def rollback(self, reason: str = "manual") -> RollbackResult:
        prev = self.state.previous_production_model_id or self.state.production_model_id
        if self.state.canary_model_id:
            # demote canary
            try:
                m = self.registry.get_manifest(self.state.canary_model_id)
                demoted = m.model_copy(update={"status": "staging"})
                path = self.registry.registry_path / f"{demoted.model_id}.json"
                import json as _json

                with open(path, "w", encoding="utf-8") as f:
                    _json.dump(demoted.model_dump(mode="json"), f, indent=2, default=str)
                self.registry._cache[demoted.model_id] = demoted
            except Exception:
                pass
        self.state.canary_model_id = None
        self.state.canary_traffic_pct = 0
        if prev:
            self.state.production_model_id = prev
        self.state.last_action = f"rollback:{reason}"
        self._save()
        return RollbackResult(
            rolled_back=True,
            reason=reason,
            active_production=self.state.production_model_id,
            state=self.state.to_dict(),
        )

    def choose_model(self, default_model_id: str, rand_pct: int | None = None) -> str:
        """Simple traffic split: if canary set and rand < traffic, use canary."""
        if not self.state.canary_model_id or self.state.canary_traffic_pct <= 0:
            return self.state.production_model_id or default_model_id
        import random

        r = random.randint(1, 100) if rand_pct is None else rand_pct
        if r <= self.state.canary_traffic_pct:
            return self.state.canary_model_id
        return self.state.production_model_id or default_model_id
