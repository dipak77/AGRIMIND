"""Tests for models package."""
import pytest
from datetime import datetime
from tokenizer.schemas import TokenizerManifest
from tokenizer.manager import TokenizerManager
from registry.schemas import ModelManifest, EvalScores
from registry.client import ModelRegistryClient
from inference.contracts import InferenceRequest, InferenceResponse
from inference.engine import InferenceEngine
import hashlib
import tempfile
import json


class TestTokenizerManifest:
    def test_create_manifest(self):
        manifest = TokenizerManifest(
            tokenizer_id="agri-tokenizer-v1",
            vocab_size=64000,
            model_family="agrimind-18m",
            checksum="sha256:abc123",
            languages=["en", "hi", "mr"]
        )
        assert manifest.is_frozen is True
        assert manifest.normalization == "NFKC"
    
    def test_verify_checksum(self):
        data = b"test tokenizer data"
        checksum = hashlib.sha256(data).hexdigest()
        manifest = TokenizerManifest(
            tokenizer_id="test",
            vocab_size=1000,
            model_family="test",
            checksum=checksum,
            languages=["en"]
        )
        assert manifest.verify_checksum(data) is True
        assert manifest.verify_checksum(b"wrong data") is False


class TestModelManifest:
    def test_create_model_manifest(self):
        eval_scores = EvalScores(faithfulness=0.96, safety=1.0)
        manifest = ModelManifest(
            model_id="agrimind-7b-v1",
            base_model="Qwen2.5-7B",
            tokenizer_manifest_id="tok-v1",
            dataset_manifest_id="ds-v1",
            training_config="lora_r16",
            eval_score=eval_scores,
            artifact_path="s3://models/7b/v1"
        )
        assert manifest.can_promote() is True
        assert manifest.status == "staging"
    
    def test_cannot_promote_low_scores(self):
        eval_scores = EvalScores(faithfulness=0.80, safety=0.9)
        manifest = ModelManifest(
            model_id="bad-model",
            base_model="test",
            tokenizer_manifest_id="tok-v1",
            dataset_manifest_id="ds-v1",
            training_config="test",
            eval_score=eval_scores,
            artifact_path="s3://test"
        )
        assert manifest.can_promote() is False


class TestInferenceContracts:
    @pytest.mark.asyncio
    async def test_inference_request_response(self):
        request = InferenceRequest(
            model_id="test-model",
            prompt="What is the weather?",
            max_tokens=100
        )
        assert request.request_id is not None
        assert request.stream is False
    
    @pytest.mark.asyncio
    async def test_inference_engine(self):
        engine = InferenceEngine(
            model_id="test-model",
            endpoint="http://localhost:8000"
        )
        request = InferenceRequest(
            model_id="test-model",
            prompt="Test prompt"
        )
        response = await engine.generate(request)
        assert response.model_id == "test-model"
        assert response.completion is not None


class TestModelRegistryClient:
    def test_register_and_get_manifest(self, tmp_path):
        client = ModelRegistryClient(str(tmp_path))
        eval_scores = EvalScores(faithfulness=0.96, safety=1.0)
        manifest = ModelManifest(
            model_id="test-model",
            base_model="test",
            tokenizer_manifest_id="tok-v1",
            dataset_manifest_id="ds-v1",
            training_config="test",
            eval_score=eval_scores,
            artifact_path="s3://test"
        )
        
        client.register_model(manifest)
        retrieved = client.get_manifest("test-model")
        assert retrieved.model_id == "test-model"
        assert retrieved.eval_score.faithfulness == 0.96


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
