"""Tokenizer training module for KrishiMini multilingual vocabularies (P0.1)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import List, Sequence

from tokenizer.manifest import TokenizerManifest
from tokenizer.normalization import normalize_text


class SimpleSubwordTokenizer:
    """Fallback subword BPE/WordPiece style tokenizer for offline/lightweight environments."""

    def __init__(self, vocab: List[str], special_tokens: List[str] | None = None) -> None:
        self.special_tokens = special_tokens or ["<pad>", "<unk>", "<s>", "</s>"]
        self.vocab = list(self.special_tokens) + [v for v in vocab if v not in self.special_tokens]
        self.token_to_id = {t: i for i, t in enumerate(self.vocab)}
        self.id_to_token = {i: t for i, t in enumerate(self.vocab)}
        self.unk_id = self.token_to_id.get("<unk>", 1)

    def encode(self, text: str) -> List[int]:
        normalized = normalize_text(text)
        words = re.findall(r"\w+|[^\w\s]", normalized, re.UNICODE)
        ids = []
        for word in words:
            if word in self.token_to_id:
                ids.append(self.token_to_id[word])
            else:
                # Character fallback
                matched = False
                for ch in word:
                    if ch in self.token_to_id:
                        ids.append(self.token_to_id[ch])
                        matched = True
                if not matched:
                    ids.append(self.unk_id)
        return ids

    def decode(self, ids: Sequence[int]) -> str:
        tokens = [self.id_to_token.get(i, "<unk>") for i in ids]
        return " ".join(t for t in tokens if t not in self.special_tokens)

    def serialize(self) -> bytes:
        data = {
            "vocab": self.vocab,
            "special_tokens": self.special_tokens,
        }
        return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")


def train_tokenizer(
    corpus_texts: Sequence[str],
    target_vocab_size: int = 16000,
    tokenizer_id: str = "krishimini-tokenizer-16k",
    languages: List[str] | None = None,
) -> tuple[SimpleSubwordTokenizer, TokenizerManifest, bytes]:
    """Train a subword tokenizer on a corpus, returning model, manifest, and binary blob."""
    # Collect word/character frequencies across corpus
    freqs: dict[str, int] = {}
    for text in corpus_texts:
        norm = normalize_text(text)
        tokens = re.findall(r"\w+|[^\w\s]", norm, re.UNICODE)
        for t in tokens:
            freqs[t] = freqs.get(t, 0) + 1

    sorted_words = [w for w, _ in sorted(freqs.items(), key=lambda item: item[1], reverse=True)]
    
    # Cap to target vocab size minus special tokens
    special_tokens = ["<pad>", "<unk>", "<s>", "</s>"]
    max_vocab = max(100, target_vocab_size - len(special_tokens))
    vocab = sorted_words[:max_vocab]

    tok = SimpleSubwordTokenizer(vocab=vocab, special_tokens=special_tokens)
    data = tok.serialize()
    checksum = hashlib.sha256(data).hexdigest()

    manifest = TokenizerManifest(
        tokenizer_id=tokenizer_id,
        vocab_size=len(tok.vocab),
        model_family="krishimini",
        checksum=checksum,
        languages=languages or ["en", "hi", "mr"],
        normalization="NFKC",
    )

    return tok, manifest, data
