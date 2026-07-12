"""Upload the normalized real corpus + generated manifest to MinIO (Phase C).

Idempotent: objects overwrite under their normalized keys, manifest.yaml is
regenerated from the tree every run. Originals on disk stay untouched.

    uv run python -m common.corpus_upload [tree_root]
"""

from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path

from minio import Minio

from common.corpus_catalog import walk_corpus
from common.manifest_gen import generate_manifest
from common.settings import corpus_bucket, minio_credentials, minio_endpoint

MANIFEST_KEY = "manifest.yaml"


def upload_corpus(root: Path) -> int:
    entries = walk_corpus(root)
    problems = [e for e in entries if not e.is_pdf or "unrecognized-layout" in e.anomalies]
    if problems:
        for e in problems:
            print(f"REFUSING: {e.source_path} → {e.anomalies}", file=sys.stderr)
        raise SystemExit("corpus contains unrecognized/non-PDF files — fix before upload")

    manifest_yaml = generate_manifest(entries)

    access_key, secret_key = minio_credentials()
    client = Minio(minio_endpoint(), access_key=access_key, secret_key=secret_key, secure=False)
    bucket = corpus_bucket()
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)

    for entry in entries:
        client.fput_object(bucket, entry.normalized_key, str(root / entry.source_path))
    payload = manifest_yaml.encode("utf-8")
    client.put_object(bucket, MANIFEST_KEY, BytesIO(payload), length=len(payload))
    print(f"uploaded {len(entries)} objects + {MANIFEST_KEY} to bucket {bucket!r}")
    return len(entries)


if __name__ == "__main__":
    upload_corpus(Path(sys.argv[1] if len(sys.argv) > 1 else "../data/corpus/real_data"))
