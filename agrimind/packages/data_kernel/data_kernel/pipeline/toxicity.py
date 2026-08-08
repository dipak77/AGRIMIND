"""Toxicity / safety content filter (Phase 2 stage 6)."""

from __future__ import annotations

import re
from dataclasses import dataclass


# Conservative block patterns for agri pipeline (not a full moderation model).
# NOTE: do NOT match bare "rape" — oilseed rape / brassica is common agri content.
_BLOCK_PATTERNS = [
    re.compile(r"\bkill yourself\b", re.I),
    re.compile(r"\b(commit\s+)?suicide\b", re.I),
    re.compile(r"\bmake (a )?bomb\b", re.I),
    re.compile(r"\bhow to poison (a |the )?human\b", re.I),
    re.compile(r"\b(gang\s+)?rape(s|d|ing)?\b(?!\s+(seed|oil|cake))", re.I),
    re.compile(r"\boilseed\s+rape\b|\brape\s+(seed|oil|cake)\b", re.I),  # agri allowlist probe below
    re.compile(r"\bchild porn\b", re.I),
]

# Patterns that look like "rape" but are agri crop terms — never block
_AGRI_RAPE_ALLOW = re.compile(
    r"\b(oilseed\s+rape|rape\s+seed|rape\s+oil|rape\s+cake|brassica\s+napus|canola)\b",
    re.I,
)

# High-risk chemical self-harm / illegal manufacture cues
_CHEM_ABUSE = re.compile(
    r"\b(synthesize|manufacture)\s+(meth|heroin|fentanyl)\b", re.I
)


@dataclass
class ToxicityResult:
    is_safe: bool
    score: float  # 1.0 = safe, 0.0 = toxic
    flags: list[str]


class ToxicityFilter:
    def check(self, text: str) -> ToxicityResult:
        flags: list[str] = []
        body = text or ""
        # Strip common agri crop phrases so "oilseed rape" never triggers violence filter
        scrubbed = _AGRI_RAPE_ALLOW.sub(" oilseed_crop ", body)
        for pat in _BLOCK_PATTERNS:
            # skip the agri-allow probe pattern itself
            if "oilseed" in pat.pattern and "rape" in pat.pattern:
                continue
            if pat.search(scrubbed):
                flags.append(f"blocked_pattern:{pat.pattern}")
        if _CHEM_ABUSE.search(scrubbed):
            flags.append("blocked_chemical_abuse")
        if flags:
            return ToxicityResult(is_safe=False, score=0.0, flags=flags)
        return ToxicityResult(is_safe=True, score=1.0, flags=[])
