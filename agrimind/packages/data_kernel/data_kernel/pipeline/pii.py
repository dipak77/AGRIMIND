"""PII redaction for curation (India-focused)."""

from __future__ import annotations

import re
from dataclasses import dataclass

PHONE_RE = re.compile(r"\b(?:\+91[\-\s]?)?[6-9]\d{9}\b")
AADHAAR_RE = re.compile(r"\b\d{4}\s\d{4}\s\d{4}\b")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


@dataclass
class PIIResult:
    text: str
    redacted: bool
    flags: list[dict]


class PIIFilter:
    def redact(self, text: str) -> PIIResult:
        flags: list[dict] = []
        out = text
        if PHONE_RE.search(out):
            flags.append({"type": "phone", "count": len(PHONE_RE.findall(out))})
            out = PHONE_RE.sub("[REDACTED_PHONE]", out)
        if AADHAAR_RE.search(out):
            flags.append({"type": "aadhaar", "count": len(AADHAAR_RE.findall(out))})
            out = AADHAAR_RE.sub("[REDACTED_ID]", out)
        if EMAIL_RE.search(out):
            flags.append({"type": "email", "count": len(EMAIL_RE.findall(out))})
            out = EMAIL_RE.sub("[REDACTED_EMAIL]", out)
        return PIIResult(text=out, redacted=bool(flags), flags=flags)
