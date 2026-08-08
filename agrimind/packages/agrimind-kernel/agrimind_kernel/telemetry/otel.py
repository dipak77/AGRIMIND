"""OpenTelemetry setup + FastAPI middleware (Phase F2).

Offline-safe: if OTEL disabled or packages missing, no-op spans still work
via TraceContext headers.
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from typing import Any, Generator, Iterator

from agrimind_kernel.telemetry.tracing import TraceContext

_TRACER = None
_INITIALIZED = False


def otel_enabled() -> bool:
    if os.getenv("OTEL_SDK_DISABLED", "").lower() in ("1", "true", "yes"):
        return False
    if os.getenv("OTEL_ENABLED", "true").lower() in ("0", "false", "no"):
        return False
    return True


def setup_otel(service_name: str, otlp_endpoint: str | None = None) -> bool:
    """Initialize global tracer provider. Returns True if real OTEL active."""
    global _TRACER, _INITIALIZED
    if _INITIALIZED:
        return _TRACER is not None
    _INITIALIZED = True
    if not otel_enabled():
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    except ImportError:
        return False

    endpoint = otlp_endpoint or os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"
    )
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    exporter: Any = None
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    except Exception:
        # fallback console exporter for local debug
        if os.getenv("OTEL_CONSOLE_EXPORT", "").lower() in ("1", "true", "yes"):
            exporter = ConsoleSpanExporter()
    if exporter is not None:
        provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _TRACER = trace.get_tracer(service_name)
    return True


def get_tracer(service_name: str = "agrimind"):
    global _TRACER
    if _TRACER is None:
        setup_otel(service_name)
    return _TRACER


@contextmanager
def start_span(
    name: str,
    *,
    service_name: str = "agrimind",
    attributes: dict[str, Any] | None = None,
    trace_ctx: TraceContext | None = None,
) -> Generator[Any, None, None]:
    """Start an OTEL span if available; always yields a simple handle."""
    tracer = get_tracer(service_name)
    attrs = dict(attributes or {})
    if trace_ctx:
        attrs.setdefault("trace_id", trace_ctx.trace_id)
        attrs.setdefault("request_id", trace_ctx.request_id)

    if tracer is None:
        class _Noop:
            def set_attribute(self, k: str, v: Any) -> None:
                return None

            def record_exception(self, exc: BaseException) -> None:
                return None

        yield _Noop()
        return

    with tracer.start_as_current_span(name) as span:
        for k, v in attrs.items():
            try:
                span.set_attribute(k, v)
            except Exception:
                pass
        yield span


def instrument_fastapi(app: Any, service_name: str) -> None:
    """Attach HTTP middleware that records request spans + propagates trace headers."""
    setup_otel(service_name)

    @app.middleware("http")
    async def otel_middleware(request: Any, call_next: Any) -> Any:
        # build / continue trace context from headers
        raw_headers = {k: v for k, v in request.headers.items()}
        ctx = TraceContext.from_headers(raw_headers)
        ctx.service_name = service_name
        ctx.operation = f"{request.method} {request.url.path}"
        request.state.trace_ctx = ctx

        start = time.time()
        with start_span(
            f"HTTP {request.method} {request.url.path}",
            service_name=service_name,
            attributes={
                "http.method": request.method,
                "http.route": request.url.path,
                "request_id": ctx.request_id,
            },
            trace_ctx=ctx,
        ) as span:
            try:
                response = await call_next(request)
            except Exception as exc:
                span.record_exception(exc)
                raise
            elapsed_ms = (time.time() - start) * 1000
            span.set_attribute("http.status_code", response.status_code)
            span.set_attribute("duration_ms", elapsed_ms)
            # propagate
            for k, v in ctx.to_headers().items():
                response.headers[k] = v
            response.headers["X-Response-Time"] = f"{elapsed_ms/1000:.3f}s"
            return response
