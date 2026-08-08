"""Token fertility calculator for multilingual tokenizers (P0.1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence


@dataclass
class FertilityMetrics:
    total_characters: int
    total_bytes: int
    total_tokens: int
    tokens_per_character: float
    bytes_per_token: float
    token_fertility: float  # tokens per word/whitespace-delimited unit


def calculate_fertility(
    text: str,
    tokenize_fn: Callable[[str], Sequence[str | int]],
) -> FertilityMetrics:
    """Calculate token fertility metrics for a given text corpus and tokenizer."""
    if not text:
        return FertilityMetrics(
            total_characters=0,
            total_bytes=0,
            total_tokens=0,
            tokens_per_character=0.0,
            bytes_per_token=0.0,
            token_fertility=0.0,
        )

    tokens = tokenize_fn(text)
    num_tokens = len(tokens)
    num_chars = len(text)
    num_bytes = len(text.encode("utf-8"))
    words = text.split()
    num_words = len(words) if words else 1

    return FertilityMetrics(
        total_characters=num_chars,
        total_bytes=num_bytes,
        total_tokens=num_tokens,
        tokens_per_character=round(num_tokens / max(num_chars, 1), 4),
        bytes_per_token=round(num_bytes / max(num_tokens, 1), 4),
        token_fertility=round(num_tokens / max(num_words, 1), 4),
    )
