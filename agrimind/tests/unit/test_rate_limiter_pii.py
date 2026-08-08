from agrimind_kernel.security.pii import PIIRedactor
from agrimind_kernel.security.rate_limiter import InMemoryRateLimiter


def test_rate_limiter():
    lim = InMemoryRateLimiter(max_requests=2, window_seconds=60)
    assert lim.is_allowed("a") is True
    assert lim.is_allowed("a") is True
    assert lim.is_allowed("a") is False


def test_pii_redact():
    r = PIIRedactor()
    text, flags = r.redact("Call me at 9876543210 or id 1234 5678 9012")
    assert "[REDACTED_PHONE]" in text
    assert "[REDACTED_ID]" in text
    assert flags
