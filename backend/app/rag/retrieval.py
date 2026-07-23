"""pgvector retrieval over BOTH project-document chunks and regulation sections.

The live chatbot answers over two collections at once (CLAUDE.md / ARCHITECTURE
Pipeline 3): the ingested project documents (`chunks`) and the fiscal-discipline
/ procurement regulation index (`regulations`). Both carry a `vector(1024)`
BGE-M3 embedding with an HNSW cosine index, so each is a plain nearest-neighbour
query; the two candidate sets are merged and handed to the reranker.

No LLM in this path — retrieval is deterministic SQL. Every retrieved item keeps
the provenance the citation viewer needs (document + page, or regulation code +
section) so an auditor can open the real source behind any `[C#]`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class RetrievedContext:
    """One retrieved passage with the provenance a citation needs. `label` is
    assigned after reranking (the `[C#]` the model cites)."""

    kind: str  # "document" | "regulation"
    text: str
    score: float  # dense cosine similarity from pgvector
    label: int = 0
    # document provenance
    chunk_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    filename: str | None = None
    doc_type: str | None = None
    page: int | None = None
    # regulation provenance
    regulation_code: str | None = None
    act_name_th: str | None = None
    section_no: str | None = None
    section_title_th: str | None = None

    @property
    def source_label_th(self) -> str:
        if self.kind == "regulation":
            title = self.section_title_th or ""
            return f"{self.act_name_th} มาตรา/ข้อ {self.section_no} {title}".strip()
        page = f" หน้า {self.page}" if self.page else ""
        return f"{self.filename or 'เอกสารโครงการ'}{page}"


def _vec_literal(vector: list[float]) -> str:
    return "[" + ",".join(map(str, vector)) + "]"


async def retrieve_chunks(
    session: AsyncSession, query_vec: list[float], k: int
) -> list[RetrievedContext]:
    rows = (
        await session.execute(
            text(
                """
                SELECT c.id, c.document_id, c.text, c.page,
                       d.filename, d.doc_type,
                       1 - (c.embedding <=> CAST(:qvec AS vector)) AS score
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE c.embedding IS NOT NULL
                ORDER BY c.embedding <=> CAST(:qvec AS vector)
                LIMIT :k
                """
            ),
            {"qvec": _vec_literal(query_vec), "k": k},
        )
    ).mappings().all()
    return [
        RetrievedContext(
            kind="document",
            text=r["text"],
            score=float(r["score"]),
            chunk_id=r["id"],
            document_id=r["document_id"],
            filename=r["filename"],
            doc_type=r["doc_type"],
            page=r["page"],
        )
        for r in rows
    ]


async def retrieve_regulations(
    session: AsyncSession, query_vec: list[float], k: int
) -> list[RetrievedContext]:
    rows = (
        await session.execute(
            text(
                """
                SELECT id, regulation_code, act_name_th, section_no,
                       section_title_th, text,
                       1 - (embedding <=> CAST(:qvec AS vector)) AS score
                FROM regulations
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> CAST(:qvec AS vector)
                LIMIT :k
                """
            ),
            {"qvec": _vec_literal(query_vec), "k": k},
        )
    ).mappings().all()
    return [
        RetrievedContext(
            kind="regulation",
            text=r["text"],
            score=float(r["score"]),
            regulation_code=r["regulation_code"],
            act_name_th=r["act_name_th"],
            section_no=r["section_no"],
            section_title_th=r["section_title_th"],
        )
        for r in rows
    ]


async def retrieve_candidates(
    session: AsyncSession, query_vec: list[float], k: int
) -> list[RetrievedContext]:
    """Union of the top-k from each collection (reranker sorts the merge)."""
    chunks = await retrieve_chunks(session, query_vec, k)
    regulations = await retrieve_regulations(session, query_vec, k)
    return chunks + regulations


def apply_rerank(
    candidates: list[RetrievedContext], scores: list[float], top_n: int
) -> list[RetrievedContext]:
    """Keep the reranker's top-n, sorted by rerank score, and assign the stable
    1-based `[C#]` labels the prompt and citations share."""
    for candidate, score in zip(candidates, scores, strict=False):
        candidate.score = score
    ranked = sorted(candidates, key=lambda c: c.score, reverse=True)[:top_n]
    for i, candidate in enumerate(ranked, start=1):
        candidate.label = i
    return ranked
