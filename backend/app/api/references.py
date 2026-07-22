"""Citation + regulation resolution — the one-click verify path.

Every `Citation.chunk_id` in a served RiskResult already passed the guardrails
citation-existence check, so these lookups are how the UI shows the source
passage behind a claim. Regulation codes contain slashes
(e.g. "fiscal-discipline-act-2561/s.37"), hence the `:path` converter.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.schemas import ChunkOut, DocumentOut, RegulationOut
from app.core.dependencies import SessionDep, get_current_user
from app.db import queries

router = APIRouter(tags=["references"], dependencies=[Depends(get_current_user)])


@router.get("/chunks/{chunk_id}", response_model=ChunkOut)
async def get_chunk(chunk_id: uuid.UUID, session: SessionDep) -> ChunkOut:
    chunk = await queries.get_chunk(session, chunk_id)
    if chunk is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="ไม่พบเอกสารอ้างอิง")
    return ChunkOut(
        id=chunk.id,
        document_id=chunk.document_id,
        chunk_index=chunk.chunk_index,
        text=chunk.text,
        page=chunk.page,
        language=chunk.language,
        document=DocumentOut.model_validate(chunk.document),
    )


@router.get("/regulations/{regulation_code:path}", response_model=RegulationOut)
async def get_regulation(regulation_code: str, session: SessionDep) -> RegulationOut:
    regulation = await queries.get_regulation(session, regulation_code)
    if regulation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="ไม่พบข้อกฎหมายที่อ้างอิง")
    return RegulationOut.model_validate(regulation)
