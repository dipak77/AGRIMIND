"""D3: Eval harness blocks bad model promotions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def run(
    registry_path: str,
    model_id: str,
    *,
    target_status: str = "production",
    min_faithfulness: float = 0.90,
    min_safety: float = 1.0,
) -> dict:
    # Ensure models package imports work
    root = Path(__file__).resolve().parents[3] / "models"
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from registry.client import ModelRegistryClient
    from registry.gates import evaluate_promotion

    client = ModelRegistryClient(registry_path)
    client.ensure_seed_defaults()
    manifest = client.get_manifest(model_id)
    decision = evaluate_promotion(
        manifest,
        min_faithfulness=min_faithfulness,
        min_safety=min_safety,
        target_status=target_status,
    )
    result = {
        "model_id": model_id,
        "allowed": decision.allowed,
        "reasons": decision.reasons,
        "eval_score": decision.eval_score,
        "target_status": target_status,
    }
    if decision.allowed:
        print(f"PASS promotion gate: {model_id} → {target_status}")
    else:
        print(f"BLOCK promotion gate: {model_id}: {'; '.join(decision.reasons)}")
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Block bad model promotions (D3)")
    p.add_argument("--registry", default="./data/model-registry")
    p.add_argument("--model-id", required=True)
    p.add_argument("--target", default="production")
    p.add_argument("--min-faithfulness", type=float, default=0.90)
    p.add_argument("--min-safety", type=float, default=1.0)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    result = run(
        args.registry,
        args.model_id,
        target_status=args.target,
        min_faithfulness=args.min_faithfulness,
        min_safety=args.min_safety,
    )
    if args.json:
        print(json.dumps(result, indent=2))
    return 0 if result["allowed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
