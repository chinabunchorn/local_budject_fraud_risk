"""Backend settings — env-only, per the secrets rule in CLAUDE.md.

Defaults target the docker-compose stack as seen FROM THE HOST (uvicorn on the
dev machine). Inside compose the service receives compose-internal hostnames
via environment variables, which always win over these defaults.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    database_url: str = Field(
        default="postgresql+psycopg://mission3:change-me-postgres@localhost:5432/mission3",
        validation_alias=AliasChoices("BACKEND_DATABASE_URL", "DATABASE_URL"),
    )
    redis_url: str = Field(
        default="redis://:change-me-redis@localhost:6379/0",
        validation_alias=AliasChoices("BACKEND_REDIS_URL", "REDIS_URL"),
    )
    jwt_secret: str = Field(default="change-me-jwt-secret", validation_alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", validation_alias="JWT_ALGORITHM")
    jwt_access_token_expire_minutes: int = Field(
        default=60, validation_alias="JWT_ACCESS_TOKEN_EXPIRE_MINUTES"
    )
    # Comma-separated origins for the Next.js dev server / deployed frontend
    cors_origins: str = Field(
        default="http://localhost:3001", validation_alias="BACKEND_CORS_ORIGINS"
    )
    # Dashboard aggregates change only on batch reruns, so short TTL caching is safe
    dashboard_cache_ttl_seconds: int = Field(
        default=300, validation_alias="DASHBOARD_CACHE_TTL_SECONDS"
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
