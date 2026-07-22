"""Budget-report summary flow (deterministic, no LLM).

For each sub-district whose reports are genuine line-item budget tables, sums
the amount column and counts the rows of each yearly report, writing one
`budget_report_summaries` row per (sub_district, fiscal_year). Powers the
ภาพรวม multi-year budget-trend chart.

Scope: `INCLUDED_SUBDISTRICTS` — only Tambon Hua Khao. Tambon Tha Chang's
reports are narrative policy / audit-disclosure documents (not budget tables),
so summing them would be misleading; they are excluded by decision and would
need curated entry instead. A report must also yield >= MIN_LINE_ITEMS rows to
be summarized (a second safety against non-table reports).

Idempotent: upserts on (sub_district_id, fiscal_year). Re-running yields
identical rows.

Run:  cd pipelines && python -m flows.extract_budget_summaries
"""

from __future__ import annotations

import json

from prefect import flow, get_run_logger, task
from sqlalchemy import create_engine, text

from common.budget_report_extract import (
    MIN_LINE_ITEMS,
    sum_budget_report,
    top_line_items,
)
from common.item_extract import report_fiscal_year
from common.settings import database_url

# Sub-districts whose รายงานงบประมาณ are line-item budget tables (summable).
INCLUDED_SUBDISTRICTS: tuple[str, ...] = ("ตำบลหัวเขา",)


@task
def load_budget_reports() -> list[dict]:
    """One entry per budget_report document in an included sub-district, with
    its fiscal year (from the filename) and reconstructed chunk texts."""
    engine = create_engine(database_url())
    try:
        with engine.connect() as conn:
            docs = conn.execute(
                text(
                    """
                    SELECT d.id AS document_id, d.filename, d.sub_district_id,
                           sd.name_th AS sub_district_name
                    FROM documents d
                    JOIN sub_districts sd ON sd.id = d.sub_district_id
                    WHERE d.doc_type = 'budget_report'
                      AND d.parse_status = 'COMPLETED'
                      AND sd.name_th = ANY(:names)
                    ORDER BY d.filename
                    """
                ),
                {"names": list(INCLUDED_SUBDISTRICTS)},
            ).fetchall()

            out: list[dict] = []
            for d in docs:
                fiscal_year = report_fiscal_year(d.filename)
                if fiscal_year is None:
                    continue
                chunks = conn.execute(
                    text(
                        "SELECT text FROM chunks WHERE document_id = :d "
                        "ORDER BY page, chunk_index"
                    ),
                    {"d": d.document_id},
                ).fetchall()
                out.append(
                    {
                        "document_id": str(d.document_id),
                        "sub_district_id": str(d.sub_district_id),
                        "sub_district_name": d.sub_district_name,
                        "fiscal_year": fiscal_year,
                        "chunk_texts": [c.text for c in chunks],
                    }
                )
    finally:
        engine.dispose()
    return out


@task
def write_summary(report: dict) -> str:
    summary = sum_budget_report(report["chunk_texts"])
    if summary.project_count < MIN_LINE_ITEMS:
        return "skipped"
    engine = create_engine(database_url())
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO budget_report_summaries
                        (sub_district_id, fiscal_year, document_id,
                         total_budget, project_count, top_items)
                    VALUES (:sd, :fy, :doc, :total, :count, CAST(:top AS jsonb))
                    ON CONFLICT (sub_district_id, fiscal_year) DO UPDATE SET
                        document_id = EXCLUDED.document_id,
                        total_budget = EXCLUDED.total_budget,
                        project_count = EXCLUDED.project_count,
                        top_items = EXCLUDED.top_items,
                        extracted_at = now()
                    """
                ),
                {
                    "sd": report["sub_district_id"],
                    "fy": report["fiscal_year"],
                    "doc": report["document_id"],
                    "total": summary.total_budget,
                    "count": summary.project_count,
                    "top": json.dumps(top_line_items(summary, 3), ensure_ascii=False),
                },
            )
    finally:
        engine.dispose()
    return "written"


@flow(name="extract-budget-summaries")
def extract_budget_summaries() -> dict[str, int]:
    logger = get_run_logger()
    reports = load_budget_reports()
    tally = {"written": 0, "skipped": 0}
    for report in reports:
        outcome = write_summary(report)
        tally[outcome] += 1
        if outcome == "written":
            summary = sum_budget_report(report["chunk_texts"])
            logger.info(
                "%s FY%s: total=%s project_count=%d",
                report["sub_district_name"], report["fiscal_year"],
                f"{summary.total_budget:,.0f}", summary.project_count,
            )
    logger.info("budget-summary tally: %s", tally)
    return tally


if __name__ == "__main__":
    extract_budget_summaries()
