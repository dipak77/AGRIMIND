"""Unit tests for data kernel manifests."""

from datetime import UTC, datetime

import pytest
from data_kernel.manifests import (
    DatasetManifest,
    LicenseType,
    ModelManifest,
    SourceMetadata,
    TokenizerManifest,
)
from pydantic import HttpUrl


class TestLicenseType:
    """Test LicenseType enum."""

    def test_license_types_exist(self) -> None:
        """Test that common license types are defined."""
        assert LicenseType.CC0.value == "CC0-1.0"
        assert LicenseType.CC_BY.value == "CC-BY-4.0"
        assert LicenseType.PROPRIETARY.value == "Proprietary"


class TestSourceMetadata:
    """Test SourceMetadata model."""

    def test_create_source_metadata(self) -> None:
        """Test creating source metadata."""
        source = SourceMetadata(
            source_id="src-001",
            source_type="web",
            checksum="sha256:abc123",
            license=LicenseType.CC_BY,
            size_bytes=1024,
            url=None,
            path=None,
            robots_txt_compliant=True,
            language=None,
        )
        assert source.source_id == "src-001"
        assert source.source_type == "web"
        assert source.robots_txt_compliant is True

    def test_source_with_url(self) -> None:
        """Test source metadata with URL."""
        source = SourceMetadata(
            source_id="src-002",
            source_type="web",
            url=HttpUrl("https://example.com/data.pdf"),
            checksum="sha256:def456",
            license=LicenseType.CC0,
            size_bytes=2048,
            path=None,
            robots_txt_compliant=True,
            language=None,
        )
        assert str(source.url) == "https://example.com/data.pdf"


class TestDatasetManifest:
    """Test DatasetManifest model."""

    def test_create_dataset_manifest(self) -> None:
        """Test creating a dataset manifest."""
        source = SourceMetadata(
            source_id="src-001",
            source_type="web",
            checksum="sha256:abc123",
            license=LicenseType.CC_BY,
            size_bytes=1024,
            url=None,
            path=None,
            robots_txt_compliant=True,
            language=None,
        )
        manifest = DatasetManifest(
            name="Agriculture QA Dataset",
            version="1.0.0",
            description="Test dataset for agriculture QA",
            sources=[source],
            total_records=1000,
            total_size_bytes=1024000,
            quality_score=0.95,
            agriculture_relevance_score=0.98,
            lakehouse_path="s3://agrimind-lakehouse/datasets/qa-v1",
            pii_redacted=False,
            deduplicated=False,
            schema_version="1.0.0",
            checksum="",
            frozen=False,
            parent_manifest_id=None,
        )
        assert manifest.name == "Agriculture QA Dataset"
        assert manifest.version == "1.0.0"
        assert len(manifest.sources) == 1
        assert manifest.frozen is False

    def test_dataset_manifest_freeze(self) -> None:
        """Test freezing a dataset manifest."""
        source = SourceMetadata(
            source_id="src-001",
            source_type="pdf",
            checksum="sha256:xyz789",
            license=LicenseType.CC_BY_SA,
            size_bytes=5000,
            url=None,
            path=None,
            robots_txt_compliant=True,
            language=None,
        )
        manifest = DatasetManifest(
            name="Crop Disease Dataset",
            version="2.0.0",
            description="Dataset for crop disease identification",
            sources=[source],
            total_records=5000,
            total_size_bytes=5000000,
            quality_score=0.92,
            agriculture_relevance_score=0.96,
            lakehouse_path="s3://agrimind-lakehouse/datasets/disease-v2",
            pii_redacted=False,
            deduplicated=False,
            schema_version="1.0.0",
            checksum="",
            frozen=False,
            parent_manifest_id=None,
        )

        frozen = manifest.freeze()
        assert frozen.frozen is True
        assert len(frozen.checksum) == 64  # SHA-256 hex length

    def test_dataset_manifest_immutable(self) -> None:
        """Test that frozen manifest cannot be modified."""
        source = SourceMetadata(
            source_id="src-001",
            source_type="web",
            checksum="sha256:test",
            license=LicenseType.CC0,
            size_bytes=100,
            url=None,
            path=None,
            robots_txt_compliant=True,
            language=None,
        )
        manifest = DatasetManifest(
            name="Test",
            version="1.0.0",
            description="Test",
            sources=[source],
            total_records=10,
            total_size_bytes=1000,
            quality_score=0.9,
            agriculture_relevance_score=0.9,
            lakehouse_path="s3://test",
            frozen=True,
            checksum="sha256:frozen",
            pii_redacted=False,
            deduplicated=False,
            schema_version="1.0.0",
            parent_manifest_id=None,
        )

        with pytest.raises((ValueError, TypeError)):  # Frozen model cannot be modified
            manifest.name = "Modified"


class TestModelManifest:
    """Test ModelManifest model."""

    def test_create_model_manifest(self) -> None:
        """Test creating a model manifest."""
        manifest = ModelManifest(
            model_id="agrimind-7b-v1.0.0",
            base_model="Qwen2.5-7B",
            version="1.0.0",
            tokenizer_manifest_id="tok-v1",
            dataset_manifest_id="ds-20260101-abc123",
            training_config="lora_r16_alpha32",
            training_started_at=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
            training_completed_at=datetime(2026, 1, 1, 18, 0, tzinfo=UTC),
            eval_score={"faithfulness": 0.93, "relevance": 0.91},
            safety_score=0.98,
            hallucination_rate=0.02,
            artifact_path="s3://agrimind-models/7b/v1.0.0",
            artifact_checksum="sha256:model123",
            eval_passed=False,
            eval_timestamp=None,
            onnx_export_path=None,
            quantized=False,
            quantization_type=None,
            deployed=False,
            canary_percentage=None,
            description="",
            frozen=False,
        )

        assert manifest.model_id == "agrimind-7b-v1.0.0"
        assert manifest.eval_passed is False
        assert manifest.deployed is False

    def test_model_manifest_eval_passed(self) -> None:
        """Test marking evaluation as passed."""
        manifest = ModelManifest(
            model_id="agrimind-18m-v1.0.0",
            base_model="Custom-18M",
            version="1.0.0",
            tokenizer_manifest_id="tok-v1",
            dataset_manifest_id="ds-20260101-xyz789",
            training_config="full_finetune",
            training_started_at=datetime(2026, 1, 2, 9, 0, tzinfo=UTC),
            training_completed_at=datetime(2026, 1, 2, 15, 0, tzinfo=UTC),
            eval_score={},
            safety_score=0.99,
            hallucination_rate=0.01,
            artifact_path="s3://agrimind-models/18m/v1.0.0",
            artifact_checksum="sha256:edge123",
            eval_passed=False,
            eval_timestamp=None,
            onnx_export_path=None,
            quantized=False,
            quantization_type=None,
            deployed=False,
            canary_percentage=None,
            description="",
            frozen=False,
        )

        scores = {
            "faithfulness": 0.95,
            "relevance": 0.93,
            "safety": 1.0,
        }
        updated = manifest.mark_eval_passed(scores)

        assert updated.eval_passed is True
        assert updated.eval_score["faithfulness"] == 0.95
        assert updated.eval_timestamp is not None

    def test_model_manifest_deployment(self) -> None:
        """Test marking model as deployed."""
        manifest = ModelManifest(
            model_id="agrimind-7b-v1.0.0",
            base_model="Qwen2.5-7B",
            version="1.0.0",
            tokenizer_manifest_id="tok-v1",
            dataset_manifest_id="ds-20260101-abc123",
            training_config="lora_r16_alpha32",
            training_started_at=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
            training_completed_at=datetime(2026, 1, 1, 18, 0, tzinfo=UTC),
            eval_score={"faithfulness": 0.93},
            safety_score=0.98,
            hallucination_rate=0.02,
            artifact_path="s3://agrimind-models/7b/v1.0.0",
            artifact_checksum="sha256:model123",
            eval_passed=False,
            eval_timestamp=None,
            onnx_export_path=None,
            quantized=False,
            quantization_type=None,
            deployed=False,
            canary_percentage=None,
            description="",
            frozen=False,
        )

        updated = manifest.mark_deployed("staging", canary_percentage=5.0)

        assert updated.deployed is True
        assert "staging" in updated.deployment_environments
        assert updated.canary_percentage == 5.0


class TestTokenizerManifest:
    """Test TokenizerManifest model."""

    def test_create_tokenizer_manifest(self) -> None:
        """Test creating a tokenizer manifest."""
        manifest = TokenizerManifest(
            tokenizer_id="agrimind-tokenizer-v1",
            version="1.0.0",
            vocab_size=64000,
            model_type="BPE",
            model_family="agrimind-18m",
            languages=["en", "hi", "mr"],
            normalization="NFKC + Marathi/Hindi transliteration",
            vocab_path="s3://agrimind-tokenizers/v1/vocab.json",
            tokenizer_file_path="s3://agrimind-tokenizers/v1/tokenizer.json",
            artifact_checksum="sha256:tok123",
            add_prefix_space=False,
            lowercase=False,
            bos_token=None,
            eos_token=None,
            pad_token=None,
            unk_token=None,
            cls_token=None,
            sep_token=None,
            mask_token=None,
            merges_path=None,
            description="",
            frozen=False,
        )

        assert manifest.tokenizer_id == "agrimind-tokenizer-v1"
        assert len(manifest.languages) == 3
        assert "mr" in manifest.languages
        assert manifest.bos_token is None

    def test_tokenizer_with_special_tokens(self) -> None:
        """Test tokenizer with special tokens defined."""
        manifest = TokenizerManifest(
            tokenizer_id="agrimind-tokenizer-v2",
            version="2.0.0",
            vocab_size=128000,
            model_type="BPE",
            model_family="Qwen2.5",
            languages=["en", "hi", "mr"],
            normalization="NFKC",
            bos_token="<|endoftext|>",
            eos_token="<|endoftext|>",
            pad_token="<|pad|>",
            vocab_path="s3://agrimind-tokenizers/v2/vocab.json",
            tokenizer_file_path="s3://agrimind-tokenizers/v2/tokenizer.json",
            artifact_checksum="sha256:tok456",
            add_prefix_space=False,
            lowercase=False,
            unk_token=None,
            cls_token=None,
            sep_token=None,
            mask_token=None,
            merges_path=None,
            description="",
            frozen=False,
        )

        assert manifest.bos_token == "<|endoftext|>"
        assert manifest.eos_token == "<|endoftext|>"
        assert manifest.pad_token == "<|pad|>"
