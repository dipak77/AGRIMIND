"""Exact + near-duplicate detection with MinHash-style sketches (Phase 2 stage 8)."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field


_WORD = re.compile(r"[\w\u0900-\u097F]+", re.UNICODE)


@dataclass
class DedupResult:
    is_duplicate: bool
    content_hash: str
    near_duplicate_of: str | None = None
    reason: str | None = None
    jaccard: float | None = None


def _shingles(text: str, k: int = 3) -> set[str]:
    toks = [t.lower() for t in _WORD.findall(text or "") if len(t) > 2]
    if len(toks) < k:
        return set(toks) if toks else {"__empty__"}
    return {" ".join(toks[i : i + k]) for i in range(len(toks) - k + 1)}


def _minhash_signature(shingles: set[str], num_perm: int = 64) -> tuple[int, ...]:
    """Simple MinHash: min hash of shingle under num_perm salts."""
    sig: list[int] = []
    for i in range(num_perm):
        salt = f"mh{i}:".encode()
        mn = 2**64 - 1
        for s in shingles:
            h = int.from_bytes(hashlib.blake2b(salt + s.encode("utf-8"), digest_size=8).digest(), "big")
            if h < mn:
                mn = h
        sig.append(mn)
    return tuple(sig)


def _estimate_jaccard(sig_a: tuple[int, ...], sig_b: tuple[int, ...]) -> float:
    if not sig_a or not sig_b or len(sig_a) != len(sig_b):
        return 0.0
    equal = sum(1 for a, b in zip(sig_a, sig_b) if a == b)
    return equal / len(sig_a)


@dataclass
class DedupIndex:
    """In-process dedup index (swap for Redis/Postgres in production)."""

    seen_hashes: set[str] = field(default_factory=set)
    fingerprints: dict[str, str] = field(default_factory=dict)
    minhash_sigs: dict[str, tuple[int, ...]] = field(default_factory=dict)
    near_threshold: float = 0.85

    def content_hash(self, text: str) -> str:
        return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()

    def fingerprint(self, text: str) -> str:
        toks = sorted({t for t in text.lower().split() if len(t) > 3})
        blob = " ".join(toks[:200])
        return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]

    def check_and_add(self, text: str) -> DedupResult:
        h = self.content_hash(text)
        if h in self.seen_hashes:
            return DedupResult(
                is_duplicate=True,
                content_hash=h,
                near_duplicate_of=h,
                reason="exact_hash",
                jaccard=1.0,
            )
        fp = self.fingerprint(text)
        if fp in self.fingerprints:
            return DedupResult(
                is_duplicate=True,
                content_hash=h,
                near_duplicate_of=self.fingerprints[fp],
                reason="near_fingerprint",
                jaccard=None,
            )
        shingles = _shingles(text)
        sig = _minhash_signature(shingles)
        for other_h, other_sig in self.minhash_sigs.items():
            jac = _estimate_jaccard(sig, other_sig)
            if jac >= self.near_threshold:
                return DedupResult(
                    is_duplicate=True,
                    content_hash=h,
                    near_duplicate_of=other_h,
                    reason="minhash_near",
                    jaccard=jac,
                )
        self.seen_hashes.add(h)
        self.fingerprints[fp] = h
        self.minhash_sigs[h] = sig
        return DedupResult(is_duplicate=False, content_hash=h)
