"""Unit tests for Tokenizer Package & Benchmarking Engine (P0.1)."""

import tempfile
from pathlib import Path

from tokenizer.coverage import evaluate_agricultural_coverage
from tokenizer.evaluate import benchmark_tokenizer
from tokenizer.fertility import calculate_fertility
from tokenizer.manager import TokenizerManager
from tokenizer.manifest import TokenizerManifest
from tokenizer.normalization import normalize_text
from tokenizer.train import train_tokenizer


def test_unicode_nfkc_normalization() -> None:
    raw_hi = "गेहूूँ  की   बुवाई "
    norm_hi = normalize_text(raw_hi)
    assert norm_hi == "गेहूूँ की बुवाई"


def test_token_fertility_calculation() -> None:
    sample = "Applying urea fertilizer on cotton crop."
    # Mock simple split tokenizer
    metrics = calculate_fertility(sample, lambda s: s.split())
    assert metrics.total_characters == len(sample)
    assert metrics.total_tokens == len(sample.split())
    assert metrics.tokens_per_character > 0.0
    assert metrics.bytes_per_token > 0.0
    assert metrics.token_fertility == 1.0  # 1 token per word in word-split mock


def test_agricultural_coverage_evaluator() -> None:
    terms = ["fertilizer", "उर्वरक", "खत"]
    res = evaluate_agricultural_coverage(terms, lambda s: [s])
    assert res.total_terms == 3
    assert res.single_token_terms == 3
    assert res.coverage_ratio == 1.0


def test_tokenizer_candidate_benchmarking() -> None:
    tok, manifest, data = train_tokenizer(
        ["Wheat sowing and irrigation in Rabi season."],
        target_vocab_size=16000,
        tokenizer_id="test-tok-16k",
    )
    report = benchmark_tokenizer("test-tok-16k", 16000, tok.encode)
    assert report.tokenizer_id == "test-tok-16k"
    assert report.vocab_size == 16000
    assert report.english_fertility.total_tokens > 0
    assert report.overall_score > 0.0


def test_tokenizer_manager_and_manifest_checksum() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = TokenizerManager(tmpdir)
        seed_id = mgr.ensure_seed_default()
        manifest = mgr.load_manifest(seed_id)
        assert manifest.vocab_size == 16000  # Updated target default
        assert manifest.model_family == "krishimini"

        # Verify fail-loud checksum assertion
        data = (Path(tmpdir) / f"{seed_id}.blob").read_bytes()
        mgr.assert_checksum(seed_id, data)
