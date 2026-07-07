"""Tests for Chunk and Citation contracts."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from schemas import EMBEDDING_DIM, Chunk, Citation


def make_chunk(**overrides) -> dict:
    base = {
        "id": str(uuid4()),
        "document_id": str(uuid4()),
        "chunk_index": 0,
        "text": "รายการจัดซื้อครุภัณฑ์สำนักงานประจำปีงบประมาณ 2567",
        "page": 3,
    }
    return {**base, **overrides}


class TestChunk:
    def test_valid_chunk_defaults(self):
        chunk = Chunk.model_validate(make_chunk())
        assert chunk.language == "th"
        assert chunk.embedding is None
        assert chunk.metadata == {}

    def test_embedding_dimension_enforced(self):
        chunk = Chunk.model_validate(make_chunk(embedding=[0.1] * EMBEDDING_DIM))
        assert chunk.embedding is not None and len(chunk.embedding) == 1024

        with pytest.raises(ValidationError, match="1024"):
            Chunk.model_validate(make_chunk(embedding=[0.1] * 768))

    def test_empty_text_rejected(self):
        with pytest.raises(ValidationError):
            Chunk.model_validate(make_chunk(text=""))

    def test_negative_index_rejected(self):
        with pytest.raises(ValidationError):
            Chunk.model_validate(make_chunk(chunk_index=-1))


class TestCitation:
    def test_minimal_citation(self):
        citation = Citation.model_validate({"chunk_id": str(uuid4())})
        assert citation.quote_th is None

    def test_chunk_id_required(self):
        with pytest.raises(ValidationError):
            Citation.model_validate({"quote_th": "ข้อความอ้างอิง"})

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            Citation.model_validate({"chunk_id": str(uuid4()), "url": "http://x"})
