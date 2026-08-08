"""Phase D: inference backends, registry gates, promotion blocking."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

MODELS = Path(__file__).resolve().parents[2] / "packages" / "models"
if str(MODELS) not in sys.path:
    sys.path.insert(0, str(MODELS))

from inference.backends import GroundedSimBackend, OpenAICompatBackend, build_backend
from inference.contracts import InferenceRequest
from inference.engine import InferenceEngine
from registry.client import ModelRegistryClient
from registry.gates import (
    GateError,
    assert_can_promote,
    assert_dataset_matches_model,
    assert_model_servable,
    assert_tokenizer_matches_model,
    evaluate_promotion,
)
from registry.schemas import EvalScores, ModelManifest
from tokenizer.manager import TokenizerManager
from tokenizer.schemas import TokenizerManifest


@pytest.fixture()
def registry(tmp_path: Path) -> ModelRegistryClient:
    client = ModelRegistryClient(tmp_path / "models")
    client.ensure_seed_defaults()
    return client


def test_grounded_sim_backend_generates():
    import asyncio

    backend = GroundedSimBackend("agrimind-7b-sim-v0.1.0")
    req = InferenceRequest(model_id="agrimind-7b-sim-v0.1.0", prompt="crop rotation advice")

    async def _run():
        return await backend.generate(
            req, intent="general_advisory", lang="en", evidence="rotate crops"
        )

    resp = asyncio.run(_run())
    assert "rotate" in resp.completion.lower() or "sim-model" in resp.completion
    assert resp.usage["total_tokens"] >= 1
    assert backend.simulated is True


def test_build_backend_auto_sim_without_url():
    b = build_backend(mode="auto", model_id="m1", vllm_base_url=None)
    assert b.name == "grounded_sim"


def test_build_backend_remote_requires_url():
    with pytest.raises(ValueError, match="VLLM_BASE_URL"):
        build_backend(mode="remote", model_id="m1", vllm_base_url=None)


def test_seed_registry_and_servable(registry: ModelRegistryClient):
    m = assert_model_servable(registry, "agrimind-7b-sim-v0.1.0")
    assert m.eval_score.safety == 1.0
    models = registry.list_models()
    assert len(models) >= 3


def test_tokenizer_checksum_fail_loud(tmp_path: Path):
    mgr = TokenizerManager(tmp_path / "tok")
    data = b"tokenizer-bytes"
    checksum = hashlib.sha256(data).hexdigest()
    manifest = TokenizerManifest(
        tokenizer_id="tok-1",
        vocab_size=1000,
        model_family="test",
        checksum=checksum,
        languages=["en"],
    )
    mgr.register_tokenizer(manifest, data)
    mgr.assert_checksum("tok-1", data)
    with pytest.raises(ValueError, match="checksum"):
        mgr.assert_checksum("tok-1", b"wrong")


def test_tokenizer_model_mismatch_gate(registry: ModelRegistryClient):
    model = registry.get_manifest("agrimind-7b-sim-v0.1.0")
    assert_tokenizer_matches_model(model=model, tokenizer_id="agrimind-tokenizer-v1")
    with pytest.raises(GateError, match="Tokenizer mismatch"):
        assert_tokenizer_matches_model(model=model, tokenizer_id="other-tok")


def test_dataset_mismatch_gate(registry: ModelRegistryClient):
    model = registry.get_manifest("agrimind-7b-sim-v0.1.0")
    assert_dataset_matches_model(model=model, dataset_manifest_id="ds-2026-seed-v1")
    with pytest.raises(GateError, match="Dataset mismatch"):
        assert_dataset_matches_model(model=model, dataset_manifest_id="ds-other")


def test_promotion_blocks_bad_model(registry: ModelRegistryClient):
    bad = registry.get_manifest("agrimind-7b-bad-v0.0.1")
    decision = evaluate_promotion(bad)
    assert decision.allowed is False
    assert any("faithfulness" in r or "safety" in r for r in decision.reasons)
    with pytest.raises(GateError, match="Promotion blocked"):
        registry.promote_model("agrimind-7b-bad-v0.0.1", "production")


def test_promotion_allows_good_model(registry: ModelRegistryClient):
    good = registry.get_manifest("agrimind-7b-sim-v0.1.0")
    # can_promote on schema uses 0.95 faithfulness — seed is 0.96
    assert good.can_promote() is True
    assert_can_promote(good)
    promoted = registry.promote_model("agrimind-7b-sim-v0.1.0", "production")
    assert promoted.status == "production"


def test_engine_gates_unknown_model(registry: ModelRegistryClient):
    import asyncio

    engine = InferenceEngine(
        model_id="agrimind-7b-sim-v0.1.0",
        backend=GroundedSimBackend("agrimind-7b-sim-v0.1.0"),
        registry=registry,
        require_registry=True,
    )

    ok = asyncio.run(
        engine.generate(
            InferenceRequest(model_id="agrimind-7b-sim-v0.1.0", prompt="hello soil crop")
        )
    )
    assert ok.completion

    async def _bad():
        await engine.generate(InferenceRequest(model_id="does-not-exist", prompt="x"))

    with pytest.raises(GateError, match="Unknown model"):
        asyncio.run(_bad())


def test_promotion_gate_harness(tmp_path: Path):
    from eval.harness.promotion_gate import run

    reg = tmp_path / "reg"
    client = ModelRegistryClient(reg)
    client.ensure_seed_defaults()
    good = run(str(reg), "agrimind-7b-sim-v0.1.0")
    bad = run(str(reg), "agrimind-7b-bad-v0.0.1")
    assert good["allowed"] is True
    assert bad["allowed"] is False
