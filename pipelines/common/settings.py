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
