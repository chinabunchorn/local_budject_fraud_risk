"""Seed curated standard reference prices (curated/standard_prices.yaml).

Idempotent upsert keyed on item_key. Each row cites its reference document by
MinIO key (resolved to documents.id when the document is ingested); the
scanned source stays NEEDS_OCR — the citation is what lets an auditor open
the page and verify the curated number against the original.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import yaml
from sqlalchemy import text
from sqlalchemy.engine import Engine

from common.item_prechecks import StandardPrice

CURATED_FILE = Path(__file__).resolve().parent.parent / "curated" / "standard_prices.yaml"


def seed_standard_prices(engine: Engine, curated_file: Path = CURATED_FILE) -> int:
    entries = yaml.safe_load(curated_file.read_text(encoding="utf-8")) or []
    with engine.begin() as conn:
        for e in entries:
            doc_id = conn.execute(
                text("SELECT id FROM documents WHERE minio_key = :key"),
                {"key": e.get("source_minio_key")},
            ).scalar_one_or_none()
            conn.execute(
                text(
                    """
                    INSERT INTO standard_prices
                        (item_key, description_th, standard_unit_price, fiscal_year,
                         source_document_id, source_page, provenance)
                    VALUES (:key, :desc, :price, :fy, :doc, :page, 'CURATED')
                    ON CONFLICT (item_key) DO UPDATE SET
                        description_th = EXCLUDED.description_th,
                        standard_unit_price = EXCLUDED.standard_unit_price,
                        fiscal_year = EXCLUDED.fiscal_year,
                        source_document_id = EXCLUDED.source_document_id,
                        source_page = EXCLUDED.source_page
                    """
                ),
                {
                    "key": e["item_key"],
                    "desc": e["description_th"],
                    "price": str(e["standard_unit_price"]),
                    "fy": e.get("fiscal_year"),
                    "doc": doc_id,
                    "page": e.get("source_page"),
                },
            )
    return len(entries)


def load_standard_prices(engine: Engine) -> dict[str, StandardPrice]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT item_key, description_th, standard_unit_price FROM standard_prices")
        ).fetchall()
    return {
        r.item_key: StandardPrice(
            item_key=r.item_key,
            description_th=r.description_th,
            unit_price=Decimal(str(r.standard_unit_price)),
        )
        for r in rows
    }
