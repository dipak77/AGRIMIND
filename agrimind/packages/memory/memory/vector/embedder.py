"""Local multilingual-friendly embedder (no heavy model download).

Uses character n-gram hashing into a fixed vector space, L2-normalized.
Labeled as non-production; swap for BGE/E5 when model weights are available.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterable

_TOKEN_RE = re.compile(r"[\w\u0900-\u097F]+", re.UNICODE)


class LocalHashEmbedder:
    """Deterministic embedder for Qdrant live path without GPU/model files."""

    model_id = "agrimind-local-hash-v1"

    def __init__(self, dimension: int = 384) -> None:
        if dimension < 32:
            raise ValueError("dimension must be >= 32")
        self.dimension = dimension

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: Iterable[str]) -> list[list[float]]:
        return [self._embed_one(t or "") for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dimension
        norm_text = text.lower().strip()
        tokens = _TOKEN_RE.findall(norm_text)
        if not tokens:
            tokens = ["empty"]

        # unigrams + bigrams of characters for Hindi/Marathi robustness
        grams: list[str] = []
        for tok in tokens:
            grams.append(f"w:{tok}")
            if len(tok) >= 3:
                for i in range(len(tok) - 2):
                    grams.append(f"c3:{tok[i:i+3]}")

        for g in grams:
            h = hashlib.sha256(g.encode("utf-8")).digest()
            # two indices for sign + bucket (simhash-ish)
            idx = int.from_bytes(h[:4], "little") % self.dimension
            sign = 1.0 if (h[4] % 2 == 0) else -1.0
            weight = 1.0 + (h[5] / 255.0)
            vec[idx] += sign * weight

        # L2 normalize
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=True))
