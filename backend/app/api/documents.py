"""Source-document streaming for the citation viewer.

The reasoning-evidence viewer shows the real PDF instead of just the OCR/
Docling-extracted chunk text, jumped to the cited page via a `#page=N`
fragment on the frontend — this endpoint is what makes that possible. Content
is streamed straight from MinIO through the app (never exposing MinIO to the
browser); the stored object's content-type is unreliable (verified
application/octet-stream on real uploads) so `application/pdf` is forced here.
"""

from __future__ import annotations

import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from minio.error import S3Error
from sqlalchemy import select

from app.core.dependencies import SessionDep, get_current_user
from app.core.settings import get_settings
from app.db.models import Document
from app.services.storage import get_minio_client

router = APIRouter(
    prefix="/documents", tags=["documents"], dependencies=[Depends(get_current_user)]
)


@router.get("/{document_id}/file")
async def get_document_file(document_id: uuid.UUID, session: SessionDep) -> StreamingResponse:
    doc = (
        await session.execute(select(Document).where(Document.id == document_id))
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="ไม่พบเอกสาร")

    settings = get_settings()
    client = get_minio_client()
    try:
        resp = client.get_object(settings.minio_bucket_corpus, doc.minio_key)
    except S3Error as e:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, detail="ไม่สามารถดึงไฟล์เอกสารต้นฉบับได้"
        ) from e

    def iterfile():
        try:
            yield from resp.stream(64 * 1024)
        finally:
            resp.close()
            resp.release_conn()

    # HTTP headers are latin-1; Thai filenames (most of the corpus) must go in
    # the RFC 5987 filename* parameter, with a plain-ASCII fallback filename.
    encoded = quote(doc.filename, safe="")
    disposition = f"inline; filename=\"document.pdf\"; filename*=UTF-8''{encoded}"
    return StreamingResponse(
        iterfile(),
        media_type="application/pdf",
        headers={"Content-Disposition": disposition},
    )
