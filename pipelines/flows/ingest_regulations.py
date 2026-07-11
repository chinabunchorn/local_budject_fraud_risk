"""Regulation-corpus ingestion: Act PDFs → sections → BGE-M3 → pgvector.

Idempotent: rows upsert on `regulation_code`, so re-running the flow after a
parser or PDF change refreshes the index in place. `RegulationReference`
citations from risk scoring resolve against exactly these codes
(e.g. "procurement-act-2560/s.96") — this flow is what makes the guardrails
citation-existence check meaningful.
"""

from __future__ import annotations

from pathlib import Path

from prefect import flow, get_run_logger, task
from sqlalchemy import create_engine, text

from common.act_parser import ActSection, parse_act
from common.settings import database_url, tei_embed_url
from common.tei import TEIEmbedClient

# PDF filename in data/regulations/ → act code (see act_parser.ACTS)
ACT_PDFS: dict[str, str] = {
    "The_Fiscal_Discipline_Act_2561.pdf": "fiscal-discipline-act-2561",
    "Procurement_Act_2560.pdf": "procurement-act-2560",
}

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
def extract_sections(pdf_path: Path, act_code: str) -> list[ActSection]:
    sections = parse_act(pdf_path, act_code)
    numbers = [int(s.section_no) for s in sections if s.section_no.isdigit()]
    contiguous = numbers == list(range(1, len(numbers) + 1))
    get_run_logger().info(
        "%s: %d rows (%d numbered sections, last มาตรา %s, contiguous=%s)",
        act_code,
        len(sections),
        len(numbers),
        numbers[-1] if numbers else "-",
        contiguous,
    )
    if not contiguous:
        raise ValueError(
            f"{act_code}: section numbers not contiguous — parser missed or "
            f"false-split a มาตรา; refusing to index a broken act"
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
                    "act": section.act_name_th,
                    "sec": section.section_no,
                    "title": section.section_title_th,
                    "text": section.text,
                    "embedding": "[" + ",".join(map(str, vector)) + "]",
                },
            )
    engine.dispose()
    return len(sections)


@flow(name="ingest-regulations")
def ingest_regulations(regulations_dir: str = "../data/regulations") -> int:
    logger = get_run_logger()
    total = 0
    for pdf in sorted(Path(regulations_dir).glob("*.pdf")):
        act_code = ACT_PDFS.get(pdf.name)
        if act_code is None:
            logger.warning("skipping %s — not registered in ACT_PDFS", pdf.name)
            continue
        sections = extract_sections(pdf, act_code)
        vectors = embed_sections(sections)
        count = upsert_sections(sections, vectors)
        logger.info("%s: upserted %d regulation rows", act_code, count)
        total += count
    logger.info("total upserted: %d rows", total)
    return total


if __name__ == "__main__":
    ingest_regulations()
