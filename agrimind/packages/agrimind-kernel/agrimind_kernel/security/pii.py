"""PII redaction for India-focused farmer data."""

from __future__ import annotations

import re

PHONE_RE = re.compile(r"\b(?:\+91[\-\s]?)?[6-9]\d{9}\b")
AADHAAR_RE = re.compile(r"\b\d{4}\s\d{4}\s\d{4}\b")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


class PIIRedactor:
    def redact(self, text: str) -> tuple[str, list[dict]]:
        flags: list[dict] = []
        if PHONE_RE.search(text):
            flags.append({"type": "phone", "count": len(PHONE_RE.findall(text))})
            text = PHONE_RE.sub("[REDACTED_PHONE]", text)
        if AADHAAR_RE.search(text):
            flags.append({"type": "aadhaar", "count": len(AADHAAR_RE.findall(text))})
            text = AADHAAR_RE.sub("[REDACTED_ID]", text)
        if EMAIL_RE.search(text):
            flags.append({"type": "email", "count": len(EMAIL_RE.findall(text))})
            text = EMAIL_RE.sub("[REDACTED_EMAIL]", text)
        return text, flags

    def contains_pii(self, text: str) -> bool:
        return bool(PHONE_RE.search(text) or AADHAAR_RE.search(text) or EMAIL_RE.search(text))
