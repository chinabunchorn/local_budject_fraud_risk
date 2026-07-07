"""Document chunk and citation contracts.

Chunks are produced by the ingestion flow (Docling/Typhoon-OCR → PyThaiNLP
segmentation) and stored in the pgvector `chunks` table. A `Citation` is a
claim's pointer to a genuinely retrieved chunk — the guardrails
citation-existence check verifies every `chunk_id` against the retrieval set
before an answer reaches a user or a result reaches the database.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# BGE-M3 dense embedding dimension; must match the pgvector column.
EMBEDDING_DIM = 1024


class Chunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    document_id: UUID
    chunk_index: int = Field(ge=0)
    text: str = Field(min_length=1)
    page: int | None = Field(default=None, ge=1)
    language: str = "th"
    metadata: dict[str, Any] = Field(default_factory=dict)
    embedding: list[float] | None = None

    @field_validator("embedding")
    @classmethod
    def _embedding_dim(cls, v: list[float] | None) -> list[float] | None:
        if v is not None and len(v) != EMBEDDING_DIM:
            raise ValueError(f"embedding must have {EMBEDDING_DIM} dimensions, got {len(v)}")
        return v


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: UUID
    document_id: UUID | None = None
    page: int | None = Field(default=None, ge=1)
    quote_th: str | None = None
