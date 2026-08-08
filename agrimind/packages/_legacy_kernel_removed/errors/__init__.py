"""
Custom exception classes for AGRIMIND.

All exceptions inherit from AgrimindError for consistent error handling.
"""

from typing import Any


class AgrimindError(Exception):
    """Base exception for all AGRIMIND errors."""

    def __init__(
        self,
        message: str,
        code: str = "UNKNOWN_ERROR",
        details: dict[str, Any] | None = None,
    ):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary for JSON response."""
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


class ConfigurationError(AgrimindError):
    """Raised when configuration is invalid or missing."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            code="CONFIGURATION_ERROR",
            details=details,
        )


class ValidationError(AgrimindError):
    """Raised when data validation fails."""

    def __init__(
        self,
        message: str,
        field: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        detail_dict = details or {}
        if field:
            detail_dict["field"] = field
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            details=detail_dict,
        )


class NotFoundError(AgrimindError):
    """Raised when a requested resource is not found."""

    def __init__(
        self,
        resource_type: str,
        resource_id: str,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=f"{resource_type} with ID {resource_id} not found",
            code="NOT_FOUND",
            details={"resource_type": resource_type, "resource_id": resource_id, **(details or {})},
        )


class AuthenticationError(AgrimindError):
    """Raised when authentication fails."""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(
            message=message,
            code="AUTHENTICATION_ERROR",
        )


class AuthorizationError(AgrimindError):
    """Raised when user lacks permission for an action."""

    def __init__(self, message: str = "Permission denied"):
        super().__init__(
            message=message,
            code="AUTHORIZATION_ERROR",
        )


class RateLimitError(AgrimindError):
    """Raised when rate limit is exceeded."""

    def __init__(self, retry_after: int = 60):
        super().__init__(
            message="Rate limit exceeded",
            code="RATE_LIMIT_EXCEEDED",
            details={"retry_after_seconds": retry_after},
        )


class ServiceUnavailableError(AgrimindError):
    """Raised when a dependent service is unavailable."""

    def __init__(
        self,
        service_name: str,
        message: str | None = None,
    ):
        super().__init__(
            message=message or f"Service {service_name} is unavailable",
            code="SERVICE_UNAVAILABLE",
            details={"service_name": service_name},
        )


class DataIngestionError(AgrimindError):
    """Raised when data ingestion fails."""

    def __init__(
        self,
        source_id: str,
        reason: str,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=f"Failed to ingest data from {source_id}: {reason}",
            code="DATA_INGESTION_ERROR",
            details={"source_id": source_id, "reason": reason, **(details or {})},
        )


class ModelInferenceError(AgrimindError):
    """Raised when model inference fails."""

    def __init__(
        self,
        model_id: str,
        reason: str,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=f"Inference failed for model {model_id}: {reason}",
            code="MODEL_INFERENCE_ERROR",
            details={"model_id": model_id, "reason": reason, **(details or {})},
        )


class SafetyViolationError(AgrimindError):
    """Raised when safety policy is violated."""

    def __init__(
        self,
        violation_type: str,
        message: str,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=message,
            code="SAFETY_VIOLATION",
            details={"violation_type": violation_type, **(details or {})},
        )


class RetrievalError(AgrimindError):
    """Raised when retrieval from memory fails."""

    def __init__(
        self,
        retrieval_mode: str,
        reason: str,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=f"Retrieval failed ({retrieval_mode}): {reason}",
            code="RETRIEVAL_ERROR",
            details={"retrieval_mode": retrieval_mode, "reason": reason, **(details or {})},
        )


class GraphError(AgrimindError):
    """Raised when knowledge graph operation fails."""

    def __init__(
        self,
        operation: str,
        reason: str,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=f"Graph operation failed ({operation}): {reason}",
            code="GRAPH_ERROR",
            details={"operation": operation, "reason": reason, **(details or {})},
        )


__all__ = [
    "AgrimindError",
    "AuthenticationError",
    "AuthorizationError",
    "ConfigurationError",
    "DataIngestionError",
    "GraphError",
    "ModelInferenceError",
    "NotFoundError",
    "RateLimitError",
    "RetrievalError",
    "SafetyViolationError",
    "ServiceUnavailableError",
    "ValidationError",
]
