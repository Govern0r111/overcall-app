from __future__ import annotations

from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        repr=False,
    )

    app_env: Literal["development", "test", "production"] = "development"
    port: int = 8000
    database_url: SecretStr | None = None
    db_pool_size: int = 5
    db_max_overflow: int = 5
    supabase_url: str | None = None
    supabase_jwt_secret: SecretStr | None = None
    supabase_service_role_key: SecretStr | None = None
    ingest_key_pepper: SecretStr | None = None
    ingest_key_pepper_prev: SecretStr | None = None
    internal_token: SecretStr | None = None
    cors_origins: str = "http://localhost:5173"
    public_proxy_base_url: str = "http://localhost:8000"
    allow_real_upstream: bool = False
    openai_upstream_base_url: str = "https://api.openai.com"
    stripe_upstream_base_url: str = "https://api.stripe.com"
    max_request_body_bytes: int = 10 * 1024 * 1024
    max_response_buffer_bytes: int = 20 * 1024 * 1024
    log_queue_max: int = 5_000
    log_batch_size: int = 200
    log_flush_interval_ms: int = 1_000
    rate_limit_proxy_rps: int = 50
    rate_limit_api_rpm: int = 120
    max_inflight: int = 100
    log_retention_default_days: int = 14
    max_logs_per_user: int = 100_000
    tiktoken_cache_dir: str = ".tiktoken"
    log_level: str = "INFO"
    release: str = "local"

    @field_validator("port", "db_pool_size", "log_batch_size", "max_inflight")
    @classmethod
    def require_positive_int(cls, value: int) -> int:
        if value < 1:
            raise ValueError("must be greater than zero")
        return value

    @field_validator("db_max_overflow")
    @classmethod
    def require_non_negative_overflow(cls, value: int) -> int:
        if value < 0:
            raise ValueError("must not be negative")
        return value

    @field_validator(
        "max_request_body_bytes",
        "max_response_buffer_bytes",
        "log_queue_max",
        "log_flush_interval_ms",
        "rate_limit_proxy_rps",
        "rate_limit_api_rpm",
        "log_retention_default_days",
        "max_logs_per_user",
    )
    @classmethod
    def require_positive_limit(cls, value: int) -> int:
        if value < 1:
            raise ValueError("must be greater than zero")
        return value

    @field_validator("log_retention_default_days")
    @classmethod
    def validate_retention_days(cls, value: int) -> int:
        if not 1 <= value <= 90:
            raise ValueError("must be between 1 and 90 days")
        return value

    @field_validator("ingest_key_pepper", "ingest_key_pepper_prev", "internal_token")
    @classmethod
    def validate_secret_length(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and len(value.get_secret_value()) < 32:
            raise ValueError("must contain at least 32 characters")
        return value

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("must be a valid Python log level")
        return normalized

    @field_validator("cors_origins")
    @classmethod
    def validate_origins(cls, value: str) -> str:
        origins = [origin.strip() for origin in value.split(",") if origin.strip()]
        if "*" in origins:
            raise ValueError("wildcard CORS origins are not allowed")
        return ",".join(origins)

    @field_validator(
        "openai_upstream_base_url", "stripe_upstream_base_url", "public_proxy_base_url"
    )
    @classmethod
    def validate_http_url(cls, value: str) -> str:
        if not value.startswith(("https://", "http://")):
            raise ValueError("must be an HTTP or HTTPS URL")
        return value.rstrip("/")

    @model_validator(mode="after")
    def validate_production_secrets(self) -> Settings:
        if self.app_env == "production":
            missing = []
            if self.database_url is None:
                missing.append("DATABASE_URL")
            if self.supabase_url is None:
                missing.append("SUPABASE_URL")
            if self.ingest_key_pepper is None:
                missing.append("INGEST_KEY_PEPPER")
            if self.internal_token is None:
                missing.append("INTERNAL_TOKEN")
            if self.database_url is not None:
                database_host = urlsplit(self.database_url.get_secret_value()).hostname or ""
                if not database_host.endswith(".pooler.supabase.com"):
                    raise ValueError(
                        "Production DATABASE_URL must use the Supabase transaction pooler"
                    )
            if missing:
                raise ValueError(
                    "Missing or invalid required production settings: " + ", ".join(missing)
                )
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin for origin in self.cors_origins.split(",") if origin]

    @property
    def database_ssl(self) -> bool:
        if self.app_env == "production" or self.database_url is None:
            return True
        host = urlsplit(self.database_url.get_secret_value()).hostname
        return host not in {"localhost", "127.0.0.1", "host.docker.internal"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
