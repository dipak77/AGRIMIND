"""Tokenizer benchmarking evaluator comparing 12K, 16K, 24K candidates (P0.1)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable, Dict, Sequence

from tokenizer.coverage import evaluate_agricultural_coverage
from tokenizer.fertility import FertilityMetrics, calculate_fertility
from tokenizer.normalization import normalize_text


@dataclass
class TokenizerBenchmarkReport:
    tokenizer_id: str
    vocab_size: int
    english_fertility: FertilityMetrics
    hindi_fertility: FertilityMetrics
    marathi_fertility: FertilityMetrics
    code_mixed_fertility: FertilityMetrics
    agri_vocab_coverage_ratio: float
    overall_score: float

    def to_dict(self) -> dict:
        return asdict(self)


def benchmark_tokenizer(
    tokenizer_id: str,
    vocab_size: int,
    tokenize_fn: Callable[[str], Sequence[str | int]],
    sample_en: str = "Apply 50 kg of urea per hectare during kharif wheat sowing.",
    sample_hi: str = "गेहूं की बुवाई के समय 50 किलोग्राम यूरिया प्रति हेक्टेयर डालें।",
    sample_mr: str = "कापूस पिकासाठी हेक्टरी ५० किलो युरिया खत वापरावे.",
    sample_code_mixed: str = "Kharif season me cotton crop ko 50 kg urea do.",
) -> TokenizerBenchmarkReport:
    """Benchmark a tokenizer candidate across EN, HI, MR, and code-mixed corpora."""
    en_f = calculate_fertility(normalize_text(sample_en), tokenize_fn)
    hi_f = calculate_fertility(normalize_text(sample_hi), tokenize_fn)
    mr_f = calculate_fertility(normalize_text(sample_mr), tokenize_fn)
    cm_f = calculate_fertility(normalize_text(sample_code_mixed), tokenize_fn)

    cov = evaluate_agricultural_coverage(None, tokenize_fn)

    # Compute aggregate score favoring balanced fertility (low tokens/char) and high agri coverage
    avg_fertility = (en_f.token_fertility + hi_f.token_fertility + mr_f.token_fertility) / 3.0
    score = round((cov.coverage_ratio * 100.0) / max(avg_fertility, 0.5), 2)

    return TokenizerBenchmarkReport(
        tokenizer_id=tokenizer_id,
        vocab_size=vocab_size,
        english_fertility=en_f,
        hindi_fertility=hi_f,
        marathi_fertility=mr_f,
        code_mixed_fertility=cm_f,
        agri_vocab_coverage_ratio=cov.coverage_ratio,
        overall_score=score,
    )
