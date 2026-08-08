"""Request/trace context for cross-service propagation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass
class TraceContext:
    trace_id: str = field(default_factory=lambda: uuid4().hex)
    span_id: str = field(default_factory=lambda: uuid4().hex[:16])
    request_id: str = field(default_factory=lambda: uuid4().hex)
    service_name: str = "unknown"
    operation: str = "unknown"
    parent_span_id: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_headers(self) -> dict[str, str]:
        return {
            "X-Trace-ID": self.trace_id,
            "X-Span-ID": self.span_id,
            "X-Request-ID": self.request_id,
            "X-Service-Name": self.service_name,
        }

    @classmethod
    def from_headers(cls, headers: dict[str, str]) -> TraceContext:
        # Case-insensitive header lookup helpers
        def g(*keys: str) -> str | None:
            lower = {k.lower(): v for k, v in headers.items()}
            for k in keys:
                if k.lower() in lower:
                    return lower[k.lower()]
            return None

        return cls(
            trace_id=g("X-Trace-ID", "x-trace-id") or uuid4().hex,
            span_id=g("X-Span-ID", "x-span-id") or uuid4().hex[:16],
            request_id=g("X-Request-ID", "x-request-id") or uuid4().hex,
            parent_span_id=g("X-Span-ID", "x-span-id"),
            service_name=g("X-Service-Name", "x-service-name") or "unknown",
        )
