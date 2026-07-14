"""Structured extraction flow (Phase F) — deterministic, no LLM.

Reads the already-ingested document text from `chunks`, and for each project:

  contract summary  → projects.{budget_total, reference_price, contract_price,
                        procurement_method} and the `bids` table (§6 bidders +
                        §7 winner);
  บก.01 / บก.๐๖     → cross-check ราคากลาง;
  BOQ               → grand total for the BOQ↔บก.01 check;
  → `precheck_results` (deterministic findings for Phase-G risk scoring).

Idempotent: money fields are COALESCE-updated (a failed parse never nulls a
good value), and bids/prechecks are replaced per project inside one
transaction. Re-running yields identical rows.

Run:  cd pipelines && python -m flows.extract_structured
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from prefect import flow, get_run_logger, task
from sqlalchemy import create_engine, text

from common.prechecks import BidFact, ProjectFacts, compute_prechecks
from common.settings import database_url
from common.structured_extract import (
    ContractSummary,
    parse_boq_total,
    parse_contract_summary,
    parse_reference_form,
    reconstruct,
)

# doc_types this flow reads; others (tor, tech_spec, budget_report, …) are not
# structured-extraction sources.
_FINANCIAL_DOC_TYPES = ("contract_summary", "bk01", "bk06", "boq")


@dataclass
class ProjectDocs:
    project_id: str
    name_th: str
    texts: dict[str, str]  # doc_type → reconstructed markdown (first doc of that type)
    present_doc_types: set[str]


@task
def load_projects() -> list[ProjectDocs]:
    """One ProjectDocs per project: reconstructed text for each financial
    doc_type, plus the full set of doc_types present (for expected-docs)."""
    engine = create_engine(database_url())
    try:
        with engine.connect() as conn:
            projects = conn.execute(
                text("SELECT id, name_th FROM projects ORDER BY name_th")
            ).fetchall()
            present = conn.execute(
                text(
                    "SELECT project_id, array_agg(DISTINCT doc_type) AS types "
                    "FROM documents WHERE project_id IS NOT NULL AND doc_type IS NOT NULL "
                    "GROUP BY project_id"
                )
            ).fetchall()
            present_by_project = {str(r.project_id): set(r.types) for r in present}

            rows = conn.execute(
                text(
                    """
                    SELECT d.project_id, d.doc_type, d.id AS document_id,
                           c.chunk_index, c.page, c.text
                    FROM documents d
                    JOIN chunks c ON c.document_id = d.id
                    WHERE d.project_id IS NOT NULL
                      AND d.doc_type = ANY(:types)
                      AND d.parse_status = 'COMPLETED'
                    ORDER BY d.project_id, d.doc_type, d.id, c.chunk_index
                    """
                ),
                {"types": list(_FINANCIAL_DOC_TYPES)},
            ).fetchall()
    finally:
        engine.dispose()

    # group chunks → per (project, doc_type, document) → reconstructed text.
    # keep the first document of each doc_type per project (one each in practice).
    grouped: dict[str, dict[str, dict[str, list[tuple[int, int | None, str]]]]] = {}
    for r in rows:
        pid = str(r.project_id)
        grouped.setdefault(pid, {}).setdefault(r.doc_type, {}).setdefault(
            str(r.document_id), []
        ).append((r.chunk_index, r.page, r.text))

    out: list[ProjectDocs] = []
    for pid, name in ((str(p.id), p.name_th) for p in projects):
        texts: dict[str, str] = {}
        for doc_type, docs in grouped.get(pid, {}).items():
            first_doc = next(iter(docs.values()))
            texts[doc_type] = reconstruct(first_doc)
        out.append(
            ProjectDocs(
                project_id=pid,
                name_th=name,
                texts=texts,
                present_doc_types=present_by_project.get(pid, set()),
            )
        )
    return out


def _facts(docs: ProjectDocs, summary: ContractSummary) -> ProjectFacts:
    form = parse_reference_form(docs.texts.get("bk01") or docs.texts.get("bk06") or "")
    boq_total = parse_boq_total(docs.texts.get("boq", ""))
    winner_key = (
        _match(summary.winner.name) if summary.winner else None
    )
    bids = [
        BidFact(
            name=b.name,
            amount=b.amount,
            is_winner=winner_key is not None and _match(b.name) == winner_key,
        )
        for b in summary.bidders
    ]
    contract_price = summary.winner.contract_price if summary.winner else None
    return ProjectFacts(
        procurement_method=summary.procurement_method,
        budget=summary.budget,
        reference_price=summary.reference_price,
        contract_price=contract_price,
        bids=bids,
        form_reference_price=form.reference_price,
        boq_total=boq_total,
        present_doc_types=docs.present_doc_types,
    )


def _match(name: str) -> str:
    return "".join(name.split())


@task
def extract_project(docs: ProjectDocs) -> str:
    logger = get_run_logger()
    summary_text = docs.texts.get("contract_summary")
    if not summary_text:
        logger.warning("%s: no contract summary — skipped", docs.name_th)
        return "skipped"

    summary = parse_contract_summary(summary_text)
    facts = _facts(docs, summary)
    checks = compute_prechecks(facts)

    engine = create_engine(database_url())
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE projects SET
                        budget_total = COALESCE(:budget, budget_total),
                        reference_price = COALESCE(:reference, reference_price),
                        contract_price = COALESCE(:contract, contract_price),
                        procurement_method = COALESCE(:method, procurement_method)
                    WHERE id = :pid
                    """
                ),
                {
                    "budget": summary.budget,
                    "reference": summary.reference_price,
                    "contract": facts.contract_price,
                    "method": summary.procurement_method,
                    "pid": docs.project_id,
                },
            )
            conn.execute(
                text("DELETE FROM bids WHERE project_id = :pid"), {"pid": docs.project_id}
            )
            for bid in facts.bids:
                conn.execute(
                    text(
                        """
                        INSERT INTO bids (project_id, bidder_name_th, bid_amount, is_winner)
                        VALUES (:pid, :name, :amount, :winner)
                        ON CONFLICT (project_id, bidder_name_th) DO UPDATE SET
                            bid_amount = EXCLUDED.bid_amount,
                            is_winner = EXCLUDED.is_winner
                        """
                    ),
                    {
                        "pid": docs.project_id,
                        "name": bid.name,
                        "amount": bid.amount,
                        "winner": bid.is_winner,
                    },
                )
            conn.execute(
                text(
                    """
                    INSERT INTO precheck_results (project_id, checks)
                    VALUES (:pid, CAST(:checks AS jsonb))
                    ON CONFLICT (project_id) DO UPDATE SET
                        checks = EXCLUDED.checks,
                        generated_at = now()
                    """
                ),
                {"pid": docs.project_id, "checks": json.dumps(checks, ensure_ascii=False)},
            )
    finally:
        engine.dispose()

    flags = sum(1 for c in checks if c["status"] == "FLAG")
    warns = sum(1 for c in checks if c["status"] == "WARN")
    logger.info(
        "%s: method=%s budget=%s ราคากลาง=%s contract=%s bids=%d (%d FLAG, %d WARN)",
        docs.name_th, summary.procurement_method, summary.budget,
        summary.reference_price, facts.contract_price, len(facts.bids), flags, warns,
    )
    return "extracted"


@flow(name="extract-structured")
def extract_structured() -> dict[str, int]:
    logger = get_run_logger()
    projects = load_projects()
    tally: dict[str, int] = {"extracted": 0, "skipped": 0}
    for docs in projects:
        tally[extract_project(docs)] += 1
    logger.info("structured-extraction summary: %s", tally)
    return tally


if __name__ == "__main__":
    extract_structured()
