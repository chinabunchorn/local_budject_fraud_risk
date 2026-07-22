"""Pipeline settings — env-only, per the secrets rule in CLAUDE.md.

Defaults target the docker-compose stack as seen FROM THE HOST (the Prefect
worker runs on the app VM / dev machine, not inside compose), so service
hostnames like `postgres:5432` from .env are remapped to localhost ports here
unless explicitly overridden.
"""

from __future__ import annotations

import os


def database_url() -> str:
    return os.environ.get(
        "PIPELINES_DATABASE_URL",
        "postgresql+psycopg://mission3:change-me-postgres@localhost:5432/mission3",
    )


def tei_embed_url() -> str:
    return os.environ.get("PIPELINES_TEI_EMBED_URL", "http://localhost:8081")


def minio_endpoint() -> str:
    # host:port, no scheme (MinIO SDK style)
    return os.environ.get("PIPELINES_MINIO_ENDPOINT", "localhost:9000")


def minio_credentials() -> tuple[str, str]:
    return (
        os.environ.get("MINIO_ROOT_USER", "mission3-minio"),
        os.environ.get("MINIO_ROOT_PASSWORD", "change-me-minio"),
    )


def corpus_bucket() -> str:
    return os.environ.get("MINIO_BUCKET_CORPUS", "corpus")


def vllm_base_url() -> str:
    # local end of the SSH tunnel to the LANTA compute node (ephemeral by design)
    return os.environ.get("VLLM_BASE_URL", "http://127.0.0.1:8000/v1")


def vllm_model_id() -> str:
    """Provenance recorded in risk_results.model_id and Langfuse — the real
    model, independent of whatever alias the server is started under."""
    return os.environ.get("VLLM_MODEL_ID") or os.environ.get(
        "VLLM_CHAT_MODEL", "scb10x/typhoon2.5-qwen3-30b-a3b"
    )


def vllm_served_model() -> str:
    """The OpenAI `model` field for requests — MUST equal the server's
    --served-model-name (e.g. an alias like 'typhoon-chat'), else vLLM 404s.
    Defaults to the provenance id when no alias override is set."""
    return os.environ.get("VLLM_SERVED_MODEL") or vllm_model_id()


def langfuse_config() -> dict[str, str] | None:
    """Langfuse creds for tracing, or None when unset (tracing then no-ops).

    The Prefect worker runs on the host, so the compose-internal
    `http://langfuse-web:3000` is remapped to localhost unless overridden."""
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
    if not (public_key and secret_key):
        return None
    host = os.environ.get("LANGFUSE_HOST")
    if not host:
        configured = os.environ.get("LANGFUSE_URL", "http://localhost:3000")
        host = configured.replace("langfuse-web", "localhost")
    return {"public_key": public_key, "secret_key": secret_key, "host": host}
