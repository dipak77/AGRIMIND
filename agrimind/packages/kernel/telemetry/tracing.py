"""
Distributed tracing for AGRIMIND.

Uses OpenTelemetry for end-to-end tracing across all services.
Every request must have a trace_id and span context.
"""

import logging
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class TraceContext:
    """
    Context for distributed tracing.

    Carries trace_id, span_id, and request metadata across service boundaries.
    """

    trace_id: str = field(default_factory=lambda: uuid4().hex)
    span_id: str = field(default_factory=lambda: uuid4().hex[:16])
    request_id: str = field(default_factory=lambda: uuid4().hex)
    service_name: str = "unknown"
    operation: str = "unknown"
    parent_span_id: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    def set_attribute(self, key: str, value: Any) -> None:
        """Set a trace attribute."""
        self.attributes[key] = value

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "request_id": self.request_id,
            "service_name": self.service_name,
            "operation": self.operation,
            "parent_span_id": self.parent_span_id,
            "attributes": self.attributes,
        }

    def to_headers(self) -> dict[str, str]:
        """
        Convert to HTTP headers for propagating trace context.

        These headers should be passed to downstream services.
        """
        return {
            "X-Trace-ID": self.trace_id,
            "X-Span-ID": self.span_id,
            "X-Request-ID": self.request_id,
            "X-Service-Name": self.service_name,
        }

    @classmethod
    def from_headers(cls, headers: dict[str, str]) -> "TraceContext":
        """
        Reconstruct trace context from incoming HTTP headers.

        Used by services receiving requests with existing trace context.
        """
        return cls(
            trace_id=headers.get("X-Trace-ID", uuid4().hex),
            span_id=headers.get("X-Span-ID", uuid4().hex[:16]),
            request_id=headers.get("X-Request-ID", uuid4().hex),
            parent_span_id=headers.get("X-Span-ID"),  # Current span becomes parent
            service_name=headers.get("X-Service-Name", "unknown"),
        )


class Tracer:
    """
    Simple tracer for distributed tracing.

    In production, this would wrap OpenTelemetry's Tracer.
    For now, provides basic trace context management and logging hooks.
    """

    def __init__(self, service_name: str):
        self.service_name = service_name
        self._logger = logging.getLogger(f"tracer.{service_name}")

    def start_span(
        self,
        operation: str,
        trace_context: TraceContext | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> TraceContext:
        """
        Start a new span within an existing trace or create a new trace.

        Args:
            operation: Name of the operation being traced
            trace_context: Optional parent trace context
            attributes: Optional attributes to attach to the span

        Returns:
            New TraceContext with updated span information
        """
        if trace_context is None:
            trace_context = TraceContext()

        new_context = TraceContext(
            trace_id=trace_context.trace_id,
            span_id=uuid4().hex[:16],
            request_id=trace_context.request_id,
            service_name=self.service_name,
            operation=operation,
            parent_span_id=trace_context.span_id,
            attributes=attributes or {},
        )

        self._log_event("span_started", new_context)
        return new_context

    def end_span(self, trace_context: TraceContext, success: bool = True) -> None:
        """
        End a span and log completion.

        Args:
            trace_context: The trace context to end
            success: Whether the operation succeeded
        """
        trace_context.set_attribute("success", success)
        self._log_event("span_ended", trace_context)

    @contextmanager
    def trace(
        self,
        operation: str,
        trace_context: TraceContext | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Generator[TraceContext, None, None]:
        """
        Context manager for tracing an operation.

        Usage:
            with tracer.trace("process_query", ctx) as ctx:
                # do work
                ctx.set_attribute("query_length", len(query))

        Args:
            operation: Name of the operation
            trace_context: Optional parent trace context
            attributes: Optional initial attributes

        Yields:
            TraceContext for the current span
        """
        ctx = self.start_span(operation, trace_context, attributes)
        try:
            yield ctx
            self.end_span(ctx, success=True)
        except Exception as e:
            ctx.set_attribute("error", str(e))
            self.end_span(ctx, success=False)
            raise

    def _log_event(self, event: str, ctx: TraceContext) -> None:
        """Log a trace event as structured JSON."""
        log_entry = {
            "event": event,
            **ctx.to_dict(),
        }
        self._logger.info(log_entry)


# Global tracer instance (initialized per-service)
_tracer: Tracer | None = None


def get_tracer(service_name: str) -> Tracer:
    """
    Get or create a tracer for a service.

    Args:
        service_name: Name of the service (e.g., "assistant-api", "memory-service")

    Returns:
        Tracer instance for the service
    """
    global _tracer
    if _tracer is None or _tracer.service_name != service_name:
        _tracer = Tracer(service_name)
    return _tracer


def trace_request(
    operation: str,
    request_id: str | None = None,
    headers: dict[str, str] | None = None,
) -> TraceContext:
    """
    Create trace context for an incoming request.

    This is the entry point for tracing in each service.

    Args:
        operation: Name of the operation handling the request
        request_id: Optional request ID from client
        headers: Optional incoming HTTP headers with trace context

    Returns:
        TraceContext for the request
    """
    if headers:
        ctx = TraceContext.from_headers(headers)
    else:
        ctx = TraceContext()

    if request_id:
        ctx.request_id = request_id

    return ctx


__all__ = [
    "TraceContext",
    "Tracer",
    "get_tracer",
    "trace_request",
]
