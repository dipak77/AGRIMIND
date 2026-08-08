"""Base errors for AGRIMIND services."""

from __future__ import annotations

from typing import Any


class AgrimindError(Exception):
    def __init__(
        self,
        message: str,
        code: str = "UNKNOWN_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class ConfigurationError(AgrimindError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="CONFIGURATION_ERROR", details=details)


class ValidationError(AgrimindError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="VALIDATION_ERROR", details=details)


class DownstreamError(AgrimindError):
    def __init__(self, service: str, message: str) -> None:
        super().__init__(
            message=message,
            code="DOWNSTREAM_ERROR",
            details={"service": service},
        )
