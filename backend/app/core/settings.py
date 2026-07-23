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
    # Bare host:port (no scheme), matching pipelines/common/settings.py's
    # PIPELINES_MINIO_ENDPOINT convention — the compose-internal MINIO_ENDPOINT
    # (http://minio:9000) is a different shape and not read here.
    minio_endpoint: str = Field(
        default="localhost:9000", validation_alias="BACKEND_MINIO_ENDPOINT"
    )
    minio_access_key: str = Field(
        default="mission3-minio", validation_alias="MINIO_ROOT_USER"
    )
    minio_secret_key: str = Field(
        default="change-me-minio", validation_alias="MINIO_ROOT_PASSWORD"
    )
    minio_bucket_corpus: str = Field(default="corpus", validation_alias="MINIO_BUCKET_CORPUS")

    # ---- Phase 4 live RAG chatbot -------------------------------------------
    # The local end of the SSH tunnel to the active LANTA compute node. Ephemeral
    # by design: when no Slurm job is up this refuses, and the chat endpoint
    # degrades to the "outside demonstration window" state (never an error).
    vllm_base_url: str = Field(
        default="http://localhost:8000/v1", validation_alias="VLLM_BASE_URL"
    )
    # The OpenAI `model` field sent on requests — MUST equal the server's
    # --served-model-name alias (verified live: "typhoon-chat"), else vLLM 404s.
    vllm_served_model: str = Field(
        default="typhoon-chat", validation_alias="VLLM_SERVED_MODEL"
    )
    # Provenance recorded in Langfuse traces — the real HF id, independent of the
    # served alias (mirrors pipelines/common/settings.py's split).
    vllm_model_id: str = Field(
        default="scb10x/typhoon2.5-qwen3-30b-a3b", validation_alias="VLLM_MODEL_ID"
    )
    # BGE-M3 embeddings + BGE-reranker-v2-m3, both on the app VM (TEI) — never
    # depend on LANTA being up for retrieval.
    tei_embed_url: str = Field(
        default="http://localhost:8081",
        validation_alias=AliasChoices("BACKEND_TEI_EMBED_URL", "TEI_EMBED_URL"),
    )
    tei_rerank_url: str = Field(
        default="http://localhost:8082",
        validation_alias=AliasChoices("BACKEND_TEI_RERANK_URL", "TEI_RERANK_URL"),
    )
    # Retrieval knobs. Recall wide from pgvector, then let the reranker sharpen
    # to the few passages that actually go in the prompt (fewer context tokens =
    # lower prefill = lower TTFT — a measured Phase-4 optimization lever).
    chat_retrieval_top_k: int = Field(default=10, validation_alias="CHAT_RETRIEVAL_TOP_K")
    chat_rerank_top_n: int = Field(default=6, validation_alias="CHAT_RERANK_TOP_N")
    chat_max_tokens: int = Field(default=768, validation_alias="CHAT_MAX_TOKENS")
    # Conversation turns (user+assistant pairs) the frontend replays for context.
    chat_history_turns: int = Field(default=4, validation_alias="CHAT_HISTORY_TURNS")

    @property
    def vllm_metrics_url(self) -> str:
        """vLLM's Prometheus endpoint is served at the server root, not under
        /v1 — the source of per-request queue-wait (histogram delta)."""
        base = self.vllm_base_url.rstrip("/")
        if base.endswith("/v1"):
            base = base[: -len("/v1")]
        return f"{base}/metrics"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
