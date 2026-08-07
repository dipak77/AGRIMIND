"""
Configuration management for AGRIMIND.

All configuration must use Pydantic Settings with fail-loud validation.
No service should use raw os.getenv().
"""

from functools import lru_cache

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Database connection settings."""

    postgres_dsn: PostgresDsn = Field(
        ...,
        description="PostgreSQL connection string",
        examples=["postgresql+asyncpg://user:pass@localhost:5432/agrimind"],
    )
    postgres_user: str = Field(..., description="PostgreSQL username")
    postgres_password: str = Field(..., description="PostgreSQL password")
    postgres_host: str = Field(default="localhost", description="PostgreSQL host")
    postgres_port: int = Field(default=5432, description="PostgreSQL port")
    postgres_db: str = Field(default="agrimind", description="PostgreSQL database name")

    model_config = SettingsConfigDict(env_prefix="POSTGRES_")


class MinIOSettings(BaseSettings):
    """MinIO/S3 object storage settings."""

    endpoint: str = Field(..., description="MinIO endpoint URL")
    access_key: str = Field(..., description="MinIO access key")
    secret_key: str = Field(..., description="MinIO secret key")
    bucket: str = Field(default="agrimind-data", description="Default bucket name")
    model_registry_path: str = Field(..., description="S3 path for model registry")

    model_config = SettingsConfigDict(env_prefix="MINIO_")


class Neo4jSettings(BaseSettings):
    """Neo4j graph database settings."""

    uri: str = Field(..., description="Neo4j Bolt URI")
    user: str = Field(default="neo4j", description="Neo4j username")
    password: str = Field(..., description="Neo4j password")

    model_config = SettingsConfigDict(env_prefix="NEO4J_")


class QdrantSettings(BaseSettings):
    """Qdrant vector database settings."""

    url: str = Field(..., description="Qdrant server URL")
    api_key: str | None = Field(None, description="Qdrant API key (optional)")

    model_config = SettingsConfigDict(env_prefix="QDRANT_")


class RedisSettings(BaseSettings):
    """Redis cache settings."""

    url: str = Field(default="redis://localhost:6379/0", description="Redis connection URL")

    @field_validator("url")
    @classmethod
    def validate_redis_url(cls, v: str) -> str:
        """Validate Redis URL format."""
        if not v.startswith("redis://") and not v.startswith("rediss://"):
            raise ValueError("Redis URL must start with redis:// or rediss://")
        return v

    model_config = SettingsConfigDict(env_prefix="REDIS_")


class TemporalSettings(BaseSettings):
    """Temporal workflow engine settings."""

    address: str = Field(default="localhost:7233", description="Temporal server address")

    model_config = SettingsConfigDict(env_prefix="TEMPORAL_")


class OpenTelemetrySettings(BaseSettings):
    """OpenTelemetry tracing settings."""

    exporter_otlp_endpoint: str = Field(
        default="http://localhost:4317", description="OTLP exporter endpoint"
    )
    service_name: str = Field(default="agrimind", description="Service name for traces")

    model_config = SettingsConfigDict(env_prefix="OTEL_")


class SecuritySettings(BaseSettings):
    """Security and authentication settings."""

    jwt_secret: str = Field(..., description="JWT signing secret")
    api_key_header: str = Field(default="X-API-Key", description="Header name for API key")

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        if v == "change-me-in-production":
            raise ValueError("JWT_SECRET must be changed from default in production environments")
        if len(v) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        return v

    model_config = SettingsConfigDict(env_prefix="")


class ExternalAPISettings(BaseSettings):
    """External API keys and endpoints."""

    openweather_api_key: str | None = Field(None, description="OpenWeather API key")
    agmarknet_api_key: str | None = Field(None, description="AGMARKNET API key")
    nasa_earthdata_api_key: str | None = Field(None, description="NASA Earthdata API key")

    model_config = SettingsConfigDict(env_prefix="")


class ModelSettings(BaseSettings):
    """Model configuration settings."""

    default_cloud_model: str = Field(default="agrimind-7b-v1", description="Default cloud model ID")
    default_edge_model: str = Field(default="agrimind-18m-v1", description="Default edge model ID")
    inference_service_url: str = Field(
        default="http://localhost:8001", description="Inference service URL"
    )

    model_config = SettingsConfigDict(env_prefix="")


class GatewaySettings(BaseSettings):
    """Gateway configuration settings."""

    rate_limit: int = Field(default=100, description="Requests per minute limit")
    timeout: int = Field(default=30, description="Request timeout in seconds")

    model_config = SettingsConfigDict(env_prefix="GATEWAY_")


class Settings(BaseSettings):
    """
    Main settings class aggregating all configuration sections.

    This is the single source of truth for application configuration.
    All settings are loaded from environment variables with fail-loud validation.
    """

    # General
    env: str = Field(default="local", description="Environment: local, dev, staging, production")
    log_level: str = Field(default="INFO", description="Logging level")

    # Nested settings
    database: DatabaseSettings
    minio: MinIOSettings
    neo4j: Neo4jSettings
    qdrant: QdrantSettings
    redis: RedisSettings
    temporal: TemporalSettings
    otel: OpenTelemetrySettings
    security: SecuritySettings
    external_apis: ExternalAPISettings
    models: ModelSettings
    gateway: GatewaySettings

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}")
        return v.upper()

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Uses LRU cache to avoid reloading settings on every call.
    In tests, you can override this by calling get_settings.cache_clear().

    Note: This function requires all environment variables to be set.
    Use mock settings in tests.
    """
    # Mypy type ignore for Settings() initialization - all fields come from env vars
    return Settings()  # type: ignore[call-arg]


# Convenience exports for common settings
__all__ = [
    "DatabaseSettings",
    "ExternalAPISettings",
    "GatewaySettings",
    "MinIOSettings",
    "ModelSettings",
    "Neo4jSettings",
    "OpenTelemetrySettings",
    "QdrantSettings",
    "RedisSettings",
    "SecuritySettings",
    "Settings",
    "TemporalSettings",
    "get_settings",
]
