"""Unit tests for Dataset Product Separation & Anti-Contamination Split Engine (P0.7/P0.8)."""

import tempfile
from pathlib import Path

from foundation_model.dataset.corpus_factory import CorpusFactory
from foundation_model.dataset.manifest import DatasetManifest
from foundation_model.dataset.split_engine import AntiContaminationSplitter, DocumentRecord


def test_anti_contamination_group_locking() -> None:
    splitter = AntiContaminationSplitter(train_ratio=0.85, val_ratio=0.10, test_ratio=0.05, seed=123)

    # Multilingual translation set linked by translation_group_id
    doc_en = DocumentRecord("d1", "Wheat info", "en", translation_group_id="trans-set-99")
    doc_hi = DocumentRecord("d2", "गेहूं की जानकारी", "hi", translation_group_id="trans-set-99")
    doc_mr = DocumentRecord("d3", "गव्हाची माहिती", "mr", translation_group_id="trans-set-99")

    split_en = splitter.assign_split(doc_en)
    split_hi = splitter.assign_split(doc_hi)
    split_mr = splitter.assign_split(doc_mr)

    # All translated versions MUST be assigned to the exact same split
    assert split_en == split_hi == split_mr


def test_corpus_factory_dataset_generation() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        docs = [
            DocumentRecord("d1", "Wheat sowing", "en", translation_group_id="grp-1"),
            DocumentRecord("d2", "गेहूं की बुवाई", "hi", translation_group_id="grp-1"),
            DocumentRecord("d3", "Cotton crop", "en", document_group_id="grp-2"),
        ]

        def mock_tok(txt: str) -> list[int]:
            return [len(w) for w in txt.split()]

        factory = CorpusFactory(tokenizer_fn=mock_tok, dataset_product_type="foundation_pretraining")
        manifest, stats = factory.build_dataset_product(docs, tmpdir, dataset_id="ds-test-01")

        assert manifest.dataset_id == "ds-test-01"
        assert manifest.document_count == 3
        assert manifest.token_count > 0
        assert manifest.is_frozen is True

        # Verify manifest JSON load
        loaded_manifest = DatasetManifest.load(Path(tmpdir) / "manifest.json")
        assert loaded_manifest.hash == manifest.hash
        assert loaded_manifest.token_count == manifest.token_count
