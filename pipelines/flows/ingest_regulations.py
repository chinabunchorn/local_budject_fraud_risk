"""Regulation-corpus ingestion: Act PDF → sections → BGE-M3 → pgvector.

Idempotent: rows upsert on `regulation_code`, so re-running the flow after a
parser or PDF change refreshes the index in place. `RegulationReference`
citations from risk scoring resolve against exactly these codes
(e.g. "fiscal-discipline-act-2561/s.37") — this flow is what makes the
guardrails citation-existence check meaningful.
"""

from __future__ import annotations

from pathlib import Path

from prefect import flow, get_run_logger, task
from sqlalchemy import create_engine, text

from common.act_parser import ACT_NAME_TH, ActSection, parse_act
from common.settings import database_url, tei_embed_url
from common.tei import TEIEmbedClient

_UPSERT = text(
    """
    INSERT INTO regulations
        (regulation_code, act_name_th, section_no, section_title_th, text, embedding)
    VALUES
        (:code, :act, :sec, :title, :text, CAST(:embedding AS vector))
    ON CONFLICT (regulation_code) DO UPDATE SET
        act_name_th = EXCLUDED.act_name_th,
        section_no = EXCLUDED.section_no,
        section_title_th = EXCLUDED.section_title_th,
        text = EXCLUDED.text,
        embedding = EXCLUDED.embedding
    """
)


@task
def extract_sections(pdf_path: Path) -> list[ActSection]:
    sections = parse_act(pdf_path)
    numbered = [s for s in sections if s.section_no.isdigit()]
    get_run_logger().info(
        "parsed %d rows (%d numbered sections, last มาตรา %s)",
        len(sections),
        len(numbered),
        numbered[-1].section_no if numbered else "-",
    )
    return sections


@task
def embed_sections(sections: list[ActSection]) -> list[list[float]]:
    client = TEIEmbedClient(tei_embed_url())
    try:
        # Prefix the heading context so "หมวด/ส่วนที่" wording is retrievable too
        return client.embed(
            [
                f"{s.section_title_th}\n{s.text}" if s.section_title_th else s.text
                for s in sections
            ]
        )
    finally:
        client.close()


@task
def upsert_sections(sections: list[ActSection], vectors: list[list[float]]) -> int:
    engine = create_engine(database_url())
    with engine.begin() as conn:
        for section, vector in zip(sections, vectors, strict=True):
            conn.execute(
                _UPSERT,
                {
                    "code": section.regulation_code,
                    "act": ACT_NAME_TH,
                    "sec": section.section_no,
                    "title": section.section_title_th,
                    "text": section.text,
                    "embedding": "[" + ",".join(map(str, vector)) + "]",
                },
            )
    engine.dispose()
    return len(sections)


@flow(name="ingest-regulations")
def ingest_regulations(
    pdf_path: str = "../data/regulations/The_Fiscal_Discipline_Act_2561.pdf",
) -> int:
    sections = extract_sections(Path(pdf_path))
    vectors = embed_sections(sections)
    count = upsert_sections(sections, vectors)
    get_run_logger().info("upserted %d regulation rows", count)
    return count


if __name__ == "__main__":
    ingest_regulations()
