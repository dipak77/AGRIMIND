"""Configuration management for AGRIMIND kernel."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SecuritySettings(BaseSettings):
    """Security configuration."""

    model_config = SettingsConfigDict(env_prefix="SECURITY_")

    jwt_secret: str = Field(
        ...,
        min_length=32,
        description="JWT signing secret (min 32 chars)",
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    token_expiry_minutes: int = Field(default=60, ge=1, description="Token expiry in minutes")

    def __init__(self, **kwargs: Any) -> None:
        # Provide safe local default only if not in production
        if "jwt_secret" not in kwargs:
            env_val = os.getenv("SECURITY_JWT_SECRET")
            if not env_val:
                # Only provide default for local development
                env = os.getenv("ENV", "local")
                if env == "local":
                    kwargs["jwt_secret"] = "local-dev-secret-key-min-32-chars-long!"
                else:
                    raise ValueError(
                        "SECURITY_JWT_SECRET must be set in production environments"
                    )
        super().__init__(**kwargs)


class RateLimitSettings(BaseSettings):
    """Rate limiting configuration."""

    model_config = SettingsConfigDict(env_prefix="RATE_LIMIT_")

    enabled: bool = Field(default=True, description="Enable rate limiting")
    requests_per_minute: int = Field(default=60, ge=1, description="Max requests per minute")
    redis_url: str = Field(default="redis://localhost:6379", description="Redis URL for rate limits")


class ObservabilitySettings(BaseSettings):
    """Observability configuration."""

    model_config = SettingsConfigDict(env_prefix="OBS_")

    tracing_enabled: bool = Field(default=True, description="Enable distributed tracing")
    metrics_enabled: bool = Field(default=True, description="Enable metrics collection")
    otlp_endpoint: str | None = Field(None, description="OTLP endpoint for traces/metrics")
    service_name: str = Field(default="agrimind", description="Service name for tracing")


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = Field(default="local", description="Environment (local, staging, production)")
    debug: bool = Field(default=False, description="Debug mode")

    # Nested settings
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
