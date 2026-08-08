"""Application settings — local-safe defaults, fail-loud in production."""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _local_jwt_default() -> str:
    env = os.getenv("ENV", "local").lower()
    secret = os.getenv("JWT_SECRET") or os.getenv("SECURITY_JWT_SECRET")
    if secret:
        return secret
    if env in ("local", "dev", "test"):
        return "local-dev-secret-key-min-32-chars-long!"
    raise ValueError("JWT_SECRET must be set outside local/dev/test")


class Settings(BaseSettings):
    """Flat settings for reliable env loading across all services."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    env: str = Field(default="local")
    log_level: str = Field(default="INFO")

    # Data stores
    postgres_dsn: str = Field(
        default="postgresql://agrimind:agrimind_secret_123@localhost:5432/agrimind"
    )
    # Feedback flywheel store: auto | postgres | jsonl | memory
    feedback_store: str = Field(default="auto")
    feedback_path: str = Field(default="./data/feedback/events.jsonl")
    minio_endpoint: str = Field(default="http://localhost:9000")
    minio_access_key: str = Field(default="minioadmin")
    minio_secret_key: str = Field(default="minioadmin")
    neo4j_uri: str = Field(default="bolt://localhost:7687")
    neo4j_user: str = Field(default="neo4j")
    neo4j_password: str = Field(default="agrimind123")
    qdrant_url: str = Field(default="http://localhost:6333")
    qdrant_api_key: str | None = Field(default=None)
    qdrant_collection: str = Field(default="agrimind_chunks")
    # memory retrieval: stub | live | auto
    memory_backend: str = Field(default="auto")
    embed_dim: int = Field(default=384, ge=32, le=4096)
    redis_url: str = Field(default="redis://localhost:6379/0")
    # B3 semantic retrieval cache
    semantic_cache_enabled: bool = Field(default=True)
    semantic_cache_ttl_seconds: int = Field(default=3600, ge=1)
    semantic_cache_threshold: float = Field(default=0.92, ge=0.0, le=1.0)
    temporal_address: str = Field(default="localhost:7233")
    lakehouse_root: str = Field(default="./data/lakehouse")
    object_store: str = Field(default="auto")  # auto | minio | local
    otel_exporter_otlp_endpoint: str = Field(default="http://localhost:4317")
    model_registry_path: str = Field(default="s3://agrimind-models")

    # Security
    jwt_secret: str = Field(default_factory=_local_jwt_default)
    jwt_algorithm: str = Field(default="HS256")
    rate_limit_per_minute: int = Field(default=60, ge=1)

    # Critical-path service URLs (canonical ports)
    gateway_url: str = Field(default="http://localhost:8000")
    assistant_api_url: str = Field(default="http://localhost:8001")
    agent_orchestrator_url: str = Field(default="http://localhost:8002")
    memory_service_url: str = Field(default="http://localhost:8003")
    inference_service_url: str = Field(default="http://localhost:8004")
    vision_service_url: str = Field(default="http://localhost:8005")
    feeds_service_url: str = Field(default="http://localhost:8006")
    data_ingestion_url: str = Field(default="http://localhost:8007")
    eval_service_url: str = Field(default="http://localhost:8008")
    expert_console_url: str = Field(default="http://localhost:8009")
    admin_service_url: str = Field(default="http://localhost:8010")

    default_cloud_model: str = Field(default="agrimind-7b-sim-v0.1.0")
    default_edge_model: str = Field(default="agrimind-18m-sim-v0.1.0")
    # Phase D inference
    inference_mode: str = Field(default="auto")  # auto | sim | remote
    vllm_base_url: str | None = Field(default=None)  # e.g. http://localhost:8008/v1
    vllm_api_key: str = Field(default="EMPTY")
    model_registry_local: str = Field(default="./data/model-registry")
    inference_require_registry: bool = Field(default=False)

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt(cls, v: str) -> str:
        if v in ("change-me", "change-me-in-production", "change-me-in-prod"):
            raise ValueError("JWT_SECRET must not use placeholder values")
        if len(v) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        return v

    def fail_loud_check(self) -> Settings:
        if self.env.lower() == "production" and "local-dev-secret" in self.jwt_secret:
            raise ValueError("Production must not use local JWT secret")
        return self

    # Nested-style accessors for older gateway code
    @property
    def security(self) -> Settings:
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings().fail_loud_check()
