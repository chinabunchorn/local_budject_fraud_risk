"""Document ingestion: MinIO corpus → Docling → garble routing → chunks in pgvector.

Two-pass by design (the 2FA constraint makes LANTA OCR a human-triggered step):

Pass 1 (`ingest_documents()`):
    manifest.yaml → upsert sub-districts/projects → per document:
    fetch → sha256 (skip when unchanged & COMPLETED) → Docling page extraction
    → garble detector per page → clean docs are chunked/embedded/upserted;
    docs with OCR-needing pages are copied to the OCR outbox and marked
    NEEDS_OCR. The outbox is then staged to LANTA with
    `python -m hpc_io.ocr_batch` (attended runbook step).

Pass 2 (`ingest_documents(ocr_results_dir=...)`):
    same command pointed at the fetched `ocr_results/`; garbled pages are
    replaced by their `<pdf-stem>/page_<n>.md` OCR output, then the document
    completes normally. Everything is idempotent: re-running either pass never
    duplicates rows.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from minio import Minio
from prefect import flow, get_run_logger, task
from sqlalchemy import create_engine, text

from common.chunker import chunk_pages
from common.garbled import NO_TEXT_LAYER, decide_page
from common.manifest import ManifestSubDistrict, parse_manifest
from common.settings import (
    corpus_bucket,
    database_url,
    minio_credentials,
    minio_endpoint,
    tei_embed_url,
)
from common.tei import TEIEmbedClient

MANIFEST_KEY = "manifest.yaml"

Extractor = Callable[[Path], list[str]]


def _default_extractor(pdf_path: Path) -> list[str]:
    from common.extract import extract_pdf_pages

    return extract_pdf_pages(pdf_path)


def _minio_client() -> Minio:
    access_key, secret_key = minio_credentials()
    return Minio(minio_endpoint(), access_key=access_key, secret_key=secret_key, secure=False)


@dataclass(frozen=True)
class DocumentPlan:
    minio_key: str
    doc_type: str | None
    project_id: str


@task
def load_catalog() -> list[DocumentPlan]:
    """Read manifest.yaml and upsert the sub-district/project catalog."""
    engine = create_engine(database_url())
    client = _minio_client()
    raw = client.get_object(corpus_bucket(), MANIFEST_KEY).read().decode("utf-8")
    sub_districts: list[ManifestSubDistrict] = parse_manifest(raw)

    plans: list[DocumentPlan] = []
    with engine.begin() as conn:
        for sd in sub_districts:
            sd_id = conn.execute(
                text(
                    """
                    INSERT INTO sub_districts (name_th, district_th, province_th)
                    VALUES (:name, :district, :province)
                    ON CONFLICT (name_th, district_th, province_th)
                    DO UPDATE SET name_th = EXCLUDED.name_th
                    RETURNING id
                    """
                ),
                {"name": sd.name_th, "district": sd.district_th, "province": sd.province_th},
            ).scalar_one()
            for proj in sd.projects:
                project_id = conn.execute(
                    text(
                        """
                        INSERT INTO projects
                            (sub_district_id, name_th, fiscal_year, category_th, budget_total)
                        VALUES (:sd, :name, :fy, :cat, :budget)
                        ON CONFLICT ON CONSTRAINT uq_projects_natural_key
                        DO UPDATE SET
                            category_th = EXCLUDED.category_th,
                            budget_total = EXCLUDED.budget_total
                        RETURNING id
                        """
                    ),
                    {
                        "sd": sd_id,
                        "name": proj.name_th,
                        "fy": proj.fiscal_year,
                        "cat": proj.category_th,
                        "budget": proj.budget_total,
                    },
                ).scalar_one()
                plans.extend(
                    DocumentPlan(doc.key, doc.doc_type, str(project_id))
                    for doc in proj.documents
                )
    engine.dispose()
    return plans


def _load_ocr_pages(ocr_results_dir: Path, pdf_stem: str) -> dict[int, str]:
    """OCR output convention: ocr_results/<pdf-stem>/page_<n>.md"""
    pages: dict[int, str] = {}
    doc_dir = ocr_results_dir / pdf_stem
    if doc_dir.is_dir():
        for md in doc_dir.glob("page_*.md"):
            page_no = int(md.stem.split("_")[1])
            pages[page_no] = md.read_text(encoding="utf-8")
    return pages


@task
def process_document(
    plan: DocumentPlan,
    outbox_dir: Path,
    ocr_results_dir: Path | None,
    extractor: Extractor,
) -> str:
    engine = create_engine(database_url())
    try:
        return _process_document(plan, engine, outbox_dir, ocr_results_dir, extractor)
    finally:
        engine.dispose()


def _process_document(
    plan: DocumentPlan,
    engine,
    outbox_dir: Path,
    ocr_results_dir: Path | None,
    extractor: Extractor,
) -> str:
    logger = get_run_logger()
    client = _minio_client()
    pdf_bytes = client.get_object(corpus_bucket(), plan.minio_key).read()
    sha = hashlib.sha256(pdf_bytes).hexdigest()
    filename = plan.minio_key.rsplit("/", 1)[-1]
    stem = filename.rsplit(".", 1)[0]

    with engine.begin() as conn:
        existing = conn.execute(
            text(
                "SELECT id, content_sha256, parse_status FROM documents "
                "WHERE minio_key = :key"
            ),
            {"key": plan.minio_key},
        ).one_or_none()
        if existing and existing.content_sha256 == sha and existing.parse_status == "COMPLETED":
            return "skipped"
        document_id = conn.execute(
            text(
                """
                INSERT INTO documents (project_id, minio_key, filename, doc_type, content_sha256)
                VALUES (:project, :key, :filename, :doc_type, :sha)
                ON CONFLICT (minio_key) DO UPDATE SET
                    project_id = EXCLUDED.project_id,
                    doc_type = EXCLUDED.doc_type,
                    content_sha256 = EXCLUDED.content_sha256,
                    parse_status = 'PENDING'
                RETURNING id
                """
            ),
            {
                "project": plan.project_id,
                "key": plan.minio_key,
                "filename": filename,
                "doc_type": plan.doc_type,
                "sha": sha,
            },
        ).scalar_one()

    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
        tmp.write(pdf_bytes)
        tmp.flush()
        pages = extractor(Path(tmp.name))

    reports = [decide_page(page) for page in pages]
    garbled = {no for no, report in enumerate(reports, start=1) if report.needs_ocr}
    scanned = sum(1 for r in reports if NO_TEXT_LAYER in r.reasons) >= max(1, len(pages) // 2)
    source = "SCANNED" if scanned else "BORN_DIGITAL"

    ocr_pages = _load_ocr_pages(ocr_results_dir, stem) if ocr_results_dir else {}
    unresolved = garbled - set(ocr_pages)

    if unresolved:
        outbox_dir.mkdir(parents=True, exist_ok=True)
        (outbox_dir / filename).write_bytes(pdf_bytes)
        manifest_path = outbox_dir / "outbox.json"
        entries = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        entries[filename] = {
            "minio_key": plan.minio_key,
            "sha256": sha,
            "pages_needing_ocr": sorted(unresolved),
            "reasons": {
                str(no): reports[no - 1].reasons for no in sorted(unresolved)
            },
        }
        manifest_path.write_text(json.dumps(entries, ensure_ascii=False, indent=2))
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE documents SET parse_status = 'NEEDS_OCR', source = :src, "
                    "page_count = :pages WHERE id = :id"
                ),
                {"id": document_id, "src": source, "pages": len(pages)},
            )
        logger.info("%s: %d page(s) need OCR → outbox", plan.minio_key, len(unresolved))
        return "needs_ocr"

    final_pages = [
        ocr_pages.get(no, page) if no in garbled else page
        for no, page in enumerate(pages, start=1)
    ]
    drafts = chunk_pages(final_pages)
    tei = TEIEmbedClient(tei_embed_url())
    try:
        vectors = tei.embed([d.text for d in drafts])
    finally:
        tei.close()

    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM chunks WHERE document_id = :id"), {"id": document_id}
        )
        for draft, vector in zip(drafts, vectors, strict=True):
            conn.execute(
                text(
                    """
                    INSERT INTO chunks
                        (document_id, chunk_index, text, page, language, metadata, embedding)
                    VALUES
                        (:doc, :idx, :text, :page, 'th',
                         CAST(:metadata AS jsonb), CAST(:embedding AS vector))
                    """
                ),
                {
                    "doc": document_id,
                    "idx": draft.chunk_index,
                    "text": draft.text,
                    "page": draft.page,
                    "metadata": json.dumps(
                        {"parser": "typhoon-ocr" if draft.page in garbled else "docling"}
                    ),
                    "embedding": "[" + ",".join(map(str, vector)) + "]",
                },
            )
        conn.execute(
            text(
                "UPDATE documents SET parse_status = 'COMPLETED', source = :src, "
                "page_count = :pages WHERE id = :id"
            ),
            {"id": document_id, "src": source, "pages": len(pages)},
        )
    logger.info("%s: %d chunks upserted", plan.minio_key, len(drafts))
    return "completed"


@flow(name="ingest-documents")
def ingest_documents(
    outbox_dir: str = "../data/ocr_outbox",
    ocr_results_dir: str | None = None,
    extractor: Extractor = _default_extractor,
) -> dict[str, int]:
    logger = get_run_logger()
    plans = load_catalog()
    tally: dict[str, int] = {"completed": 0, "needs_ocr": 0, "skipped": 0}
    for plan in plans:
        outcome = process_document(
            plan,
            Path(outbox_dir),
            Path(ocr_results_dir) if ocr_results_dir else None,
            extractor,
        )
        tally[outcome] += 1
    logger.info("ingestion summary: %s", tally)
    if tally["needs_ocr"]:
        logger.warning(
            "%d document(s) in the OCR outbox — stage them with "
            "`python -m hpc_io.ocr_batch stage` (see runbook), then re-run this "
            "flow with ocr_results_dir=<fetched results>",
            tally["needs_ocr"],
        )
    return tally


if __name__ == "__main__":
    ingest_documents()
