"""Unicode normalization and Devanagari text cleaning for KrishiMini tokenizer (P0.1)."""

from __future__ import annotations

import re
import unicodedata


class TextNormalizer:
    """Handles text normalization across English, Hindi, and Marathi."""

    def __init__(self, form: str = "NFKC") -> None:
        self.form = form

    def normalize(self, text: str) -> str:
        """Apply Unicode normalization (NFKC by default) and clean whitespace."""
        if not text:
            return ""
        
        # NFKC normalization standardizes Devanagari conjuncts & accents
        normalized = unicodedata.normalize(self.form, text)
        
        # Standardize whitespace without destroying line breaks if structured
        normalized = re.sub(r"[ \t]+", " ", normalized)
        normalized = re.sub(r"\n\s*\n+", "\n\n", normalized)
        return normalized.strip()

    def normalize_numbers_and_units(self, text: str) -> str:
        """Standardize common agricultural numbers, dosages, and units."""
        text = self.normalize(text)
        # Standardize kg/ha, L/acre, etc.
        text = re.sub(r"(\d+)\s*(kg|g|l|ml|ha|acre|acres|quintal|ton|t)/", r"\1 \2/", text, flags=re.IGNORECASE)
        return text


def normalize_text(text: str, form: str = "NFKC") -> str:
    return TextNormalizer(form=form).normalize(text)
