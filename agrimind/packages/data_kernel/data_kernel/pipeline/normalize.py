"""Unicode normalization + language detection (Phase 2 stage 4)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


_DEVANAGARI = re.compile(r"[\u0900-\u097F]")
_LATIN = re.compile(r"[A-Za-z]")


@dataclass
class NormalizeResult:
    text: str
    language: str  # en | hi | mr | unknown
    normalized: bool


def normalize_text(text: str) -> NormalizeResult:
    """NFKC normalize and detect en/hi/mr with lightweight heuristics."""
    if not text:
        return NormalizeResult(text="", language="unknown", normalized=False)
    norm = unicodedata.normalize("NFKC", text)
    # collapse weird spaces
    norm = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", norm)
    norm = re.sub(r"[ \t]+", " ", norm)
    lang = detect_language(norm)
    return NormalizeResult(text=norm, language=lang, normalized=norm != text)


def detect_language(text: str) -> str:
    """Heuristic en/hi/mr detection without heavy models."""
    sample = text[:4000]
    dev = len(_DEVANAGARI.findall(sample))
    lat = len(_LATIN.findall(sample))
    lower = sample.lower()

    # Marathi-leaning tokens (common)
    mr_markers = ("आहे", "करणे", "शेत", "पीक", "कापूस", "मराठी", "आणि")
    hi_markers = ("है", "क्या", "फसल", "किसान", "हिंदी", "और", "के लिए")

    if dev > 20 or (dev > 5 and dev >= lat // 3):
        mr_hits = sum(1 for m in mr_markers if m in sample)
        hi_hits = sum(1 for m in hi_markers if m in sample)
        if mr_hits > hi_hits:
            return "mr"
        if hi_hits > 0:
            return "hi"
        # default Devanagari agricultural text → hi unless strong mr
        return "hi" if hi_hits >= mr_hits else "mr"

    if lat > 10 or any(w in lower for w in ("crop", "farm", "soil", "pest", "the", "and")):
        return "en"
    if dev > 0:
        return "hi"
    return "unknown"
