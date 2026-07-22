"""MinIO client for streaming original documents to the citation viewer.

Read-only: this service never writes objects — ingestion owns that path
(pipelines/common/corpus_upload.py). Objects are stored with whatever
content-type fput_object defaulted to (application/octet-stream, verified
against the real bucket) so callers must set the response media type
explicitly rather than trust the stored metadata.
"""

from __future__ import annotations

from functools import lru_cache

from minio import Minio

from app.core.settings import get_settings


@lru_cache
def get_minio_client() -> Minio:
    s = get_settings()
    return Minio(
        s.minio_endpoint,
        access_key=s.minio_access_key,
        secret_key=s.minio_secret_key,
        secure=False,
    )
