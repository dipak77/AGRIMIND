"""
Logging middleware for AGRIMIND.

Provides structured JSON logging with automatic request ID injection.
All services must use this for consistent observability.
"""

import logging
import sys
from collections.abc import Mapping
from typing import Any

import structlog
from structlog.types import Processor


def get_request_id_from_context() -> str | None:
    """Extract request ID from structlog context if present."""
    try:
        context: dict[str, Any] = structlog.contextvars.get_contextvars()
        return context.get("request_id")
    except RuntimeError:
        # Context not available (e.g., outside async context)
        return None


def add_request_id(
    logger: Any, method_name: str, event_dict: Mapping[str, Any]
) -> Mapping[str, Any]:
    """Add request ID to log events if available in context."""
    request_id = get_request_id_from_context()
    if request_id:
        # Create a new dict with the request_id added
        result: dict[str, Any] = dict(event_dict)
        result["request_id"] = request_id
        return result
    return event_dict


def setup_logging(
    log_level: str = "INFO",
    service_name: str = "agrimind",
    json_logs: bool = True,
) -> None:
    """
    Configure structured logging for the service.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        service_name: Name of the service for log context
        json_logs: Whether to output JSON logs (True) or console logs (False)
    """
    # Common processors for all log formats
    common_processors: list[Processor] = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        add_request_id,
    ]

    if json_logs:
        # JSON format for production
        processors = common_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Console format for development
        processors = common_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, log_level.upper())),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s" if json_logs else "%(levelname)s - %(name)s - %(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )

    # Add service name to all logs
    logger = structlog.get_logger(service_name)
    logger.info("logging_initialized", log_level=log_level, json_logs=json_logs)


def get_logger(name: str) -> Any:
    """
    Get a structured logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Bound logger with consistent formatting
    """
    return structlog.get_logger(name)


__all__ = ["add_request_id", "get_logger", "setup_logging"]
