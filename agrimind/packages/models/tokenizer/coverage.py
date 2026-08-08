"""Agricultural vocabulary coverage evaluator (P0.1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence, Set


SEED_AGRI_TERMS = {
    # English
    "nitrogen", "phosphorus", "potassium", "irrigation", "pesticide", "fungicide",
    "fertilizer", "humus", "yield", "khareef", "rabi", "zaid", "soil", "sowing",
    # Hindi
    "सिंचाई", "उर्वरक", "कीटनाशक", "फसल", "मृदा", "उपज", "गेहूं", "धान", "कपास",
    # Marathi
    "शेतकरी", "पिक", "खत", "कीटकनाशक", "सिंचन", "माती", "कापूस", "सोयाबीन", "बाजरी",
}


@dataclass
class VocabularyCoverageResult:
    total_terms: int
    single_token_terms: int
    multi_token_terms: int
    coverage_ratio: float  # single token terms / total terms
    terms_breakdown: dict[str, int]


def evaluate_agricultural_coverage(
    terms: Set[str] | Sequence[str] | None,
    tokenize_fn: Callable[[str], Sequence[str | int]],
) -> VocabularyCoverageResult:
    """Evaluate how well a tokenizer handles domain-specific agricultural terms."""
    term_set = set(terms) if terms else SEED_AGRI_TERMS
    if not term_set:
        return VocabularyCoverageResult(0, 0, 0, 0.0, {})

    single_token = 0
    multi_token = 0
    breakdown = {}

    for term in term_set:
        toks = tokenize_fn(term)
        count = len(toks)
        breakdown[term] = count
        if count == 1:
            single_token += 1
        else:
            multi_token += 1

    total = len(term_set)
    ratio = round(single_token / total, 4) if total > 0 else 0.0

    return VocabularyCoverageResult(
        total_terms=total,
        single_token_terms=single_token,
        multi_token_terms=multi_token,
        coverage_ratio=ratio,
        terms_breakdown=breakdown,
    )
