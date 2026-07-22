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
from decimal import Decimal

from prefect import flow, get_run_logger, task
from sqlalchemy import create_engine, text

from common.item_extract import (
    CandidateProject,
    extract_item_lines,
    match_line_to_project,
    match_tracked_item,
    report_fiscal_year,
)
from common.item_prechecks import ItemFact, compute_item_findings
from common.prechecks import (
    BidFact,
    ProjectFacts,
    ProjectRecord,
    compute_prechecks,
    compute_yoy_findings,
    yoy_ok_finding,
)
from common.settings import database_url
from common.standard_prices import load_standard_prices, seed_standard_prices
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
    sub_district_id: str
    fiscal_year: int
    name_th: str
    texts: dict[str, str]  # doc_type → reconstructed markdown (first doc of that type)
    present_doc_types: set[str]


@dataclass
class Extracted:
    """Per-project result carried to the portfolio-level YoY + item passes."""

    project_id: str
    sub_district_id: str
    fiscal_year: int
    name_th: str
    budget: Decimal | None
    winner_name: str | None
    checks: list[dict]  # the seven single-project checks
    contract_price: Decimal | None = None
    bid_count: int = 0
    procurement_method: str | None = None


@task
def load_projects() -> list[ProjectDocs]:
    """One ProjectDocs per project: reconstructed text for each financial
    doc_type, plus the full set of doc_types present (for expected-docs)."""
    engine = create_engine(database_url())
    try:
        with engine.connect() as conn:
            projects = conn.execute(
                text(
                    "SELECT id, sub_district_id, fiscal_year, name_th "
                    "FROM projects ORDER BY name_th"
                )
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
    for p in projects:
        pid = str(p.id)
        texts: dict[str, str] = {}
        for doc_type, docs in grouped.get(pid, {}).items():
            first_doc = next(iter(docs.values()))
            texts[doc_type] = reconstruct(first_doc)
        out.append(
            ProjectDocs(
                project_id=pid,
                sub_district_id=str(p.sub_district_id),
                fiscal_year=p.fiscal_year,
                name_th=p.name_th,
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
def extract_project(docs: ProjectDocs) -> Extracted | None:
    """Extract one project: write its projects/bids rows and compute the seven
    single-project checks. Returns the record the YoY pass needs, or None when
    there is no contract summary to extract from."""
    logger = get_run_logger()
    summary_text = docs.texts.get("contract_summary")
    if not summary_text:
        logger.warning("%s: no contract summary — skipped", docs.name_th)
        return None

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
    finally:
        engine.dispose()

    flags = sum(1 for c in checks if c["status"] == "FLAG")
    warns = sum(1 for c in checks if c["status"] == "WARN")
    logger.info(
        "%s: method=%s budget=%s ราคากลาง=%s contract=%s bids=%d (%d FLAG, %d WARN)",
        docs.name_th, summary.procurement_method, summary.budget,
        summary.reference_price, facts.contract_price, len(facts.bids), flags, warns,
    )
    return Extracted(
        project_id=docs.project_id,
        sub_district_id=docs.sub_district_id,
        fiscal_year=docs.fiscal_year,
        name_th=docs.name_th,
        budget=summary.budget,
        winner_name=summary.winner.name if summary.winner else None,
        checks=checks,
        contract_price=facts.contract_price,
        bid_count=len(facts.bids),
        procurement_method=summary.procurement_method,
    )


@task
def extract_items(extracted: list[Extracted]) -> dict[str, list[dict]]:
    """Item pass: seed curated standard prices, pull tracked-item lines out of
    budget-report chunks (the quantity source the contract summaries lack),
    match each line to its project by year + sub-district + exact amount,
    upsert `project_items` with full source citation, then compute the
    item-level findings (unit-price spike / vendor lock / vs-standard),
    keyed by project_id for the precheck write."""
    logger = get_run_logger()
    engine = create_engine(database_url())
    by_id = {e.project_id: e for e in extracted}
    try:
        seeded = seed_standard_prices(engine)
        standards = load_standard_prices(engine)

        with engine.connect() as conn:
            report_chunks = conn.execute(
                text(
                    """
                    SELECT d.id AS document_id, d.filename, d.sub_district_id,
                           c.page, c.text
                    FROM documents d
                    JOIN chunks c ON c.document_id = d.id
                    WHERE d.doc_type = 'budget_report' AND d.parse_status = 'COMPLETED'
                    ORDER BY d.id, c.chunk_index
                    """
                )
            ).fetchall()

        facts: list[ItemFact] = []
        seen: set[tuple[str, str]] = set()  # overlapping chunks repeat lines
        with engine.begin() as conn:
            for r in report_chunks:
                fiscal_year = report_fiscal_year(r.filename)
                if fiscal_year is None:
                    continue
                candidates = [
                    CandidateProject(
                        project_id=e.project_id,
                        sub_district_id=e.sub_district_id,
                        fiscal_year=e.fiscal_year,
                        name_th=e.name_th,
                        contract_price=e.contract_price,
                    )
                    for e in extracted
                    if e.sub_district_id == str(r.sub_district_id)
                    and e.fiscal_year == fiscal_year
                ]
                for line in extract_item_lines(r.text, r.page):
                    project = match_line_to_project(line, candidates)
                    if project is None:
                        logger.warning(
                            "item line unmatched (%s, FY%s): %s",
                            r.filename, fiscal_year, line.quote_th[:80],
                        )
                        continue
                    if (project.project_id, line.item_key) in seen:
                        continue
                    seen.add((project.project_id, line.item_key))
                    conn.execute(
                        text(
                            """
                            INSERT INTO project_items
                                (project_id, item_key, description_th, quantity,
                                 unit_th, total_amount, source_document_id,
                                 source_page, source_quote_th)
                            VALUES (:pid, :key, :desc, :qty, :unit, :total,
                                    :doc, :page, :quote)
                            ON CONFLICT (project_id, item_key) DO UPDATE SET
                                description_th = EXCLUDED.description_th,
                                quantity = EXCLUDED.quantity,
                                unit_th = EXCLUDED.unit_th,
                                total_amount = EXCLUDED.total_amount,
                                source_document_id = EXCLUDED.source_document_id,
                                source_page = EXCLUDED.source_page,
                                source_quote_th = EXCLUDED.source_quote_th,
                                extracted_at = now()
                            """
                        ),
                        {
                            "pid": project.project_id,
                            "key": line.item_key,
                            "desc": line.description_th,
                            "qty": line.quantity,
                            "unit": line.unit_th,
                            "total": line.total_amount,
                            "doc": r.document_id,
                            "page": line.page,
                            "quote": line.quote_th,
                        },
                    )
                    e = by_id[project.project_id]
                    tracked = match_tracked_item(line.description_th)
                    facts.append(
                        ItemFact(
                            project_id=e.project_id,
                            sub_district_id=e.sub_district_id,
                            fiscal_year=e.fiscal_year,
                            project_name_th=e.name_th,
                            item_key=line.item_key,
                            label_th=tracked.label_th if tracked else line.item_key,
                            quantity=line.quantity,
                            unit_th=line.unit_th,
                            unit_price=line.total_amount / line.quantity,
                            total_amount=line.total_amount,
                            winner_name=e.winner_name,
                            bid_count=e.bid_count,
                            procurement_method=e.procurement_method,
                        )
                    )
    finally:
        engine.dispose()

    findings = compute_item_findings(facts, standards)
    flagged = sum(1 for fs in findings.values() for f in fs if f["status"] == "FLAG")
    logger.info(
        "item pass: %d standard price(s) seeded, %d item line(s) matched, "
        "%d FLAG finding(s)",
        seeded, len(facts), flagged,
    )
    return findings


@task
def write_precheck_results(project_id: str, checks: list[dict]) -> str:
    """Upsert the full checks array (seven single-project + the YoY finding).
    THE write path into precheck_results — idempotent on project_id."""
    engine = create_engine(database_url())
    try:
        with engine.begin() as conn:
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
                {"pid": project_id, "checks": json.dumps(checks, ensure_ascii=False)},
            )
    finally:
        engine.dispose()
    return next((c["status"] for c in checks if c["name"] == "yoy_budget_anomaly"), "OK")


@flow(name="extract-structured")
def extract_structured() -> dict[str, int]:
    logger = get_run_logger()
    docs = load_projects()
    extracted = [e for e in (extract_project(d) for d in docs) if e is not None]

    # portfolio-level YoY redundancy + contractor concentration over the curated
    # projects/bids (no PDF parsing) — the 8th check, attached per project.
    records = [
        ProjectRecord(
            project_id=e.project_id,
            sub_district_id=e.sub_district_id,
            fiscal_year=e.fiscal_year,
            name_th=e.name_th,
            budget=e.budget,
            winner=e.winner_name,
        )
        for e in extracted
    ]
    yoy = compute_yoy_findings(records)
    item_findings = extract_items(extracted)

    yoy_flagged = 0
    for e in extracted:
        finding = yoy.get(e.project_id, yoy_ok_finding())
        if finding["status"] == "FLAG":
            yoy_flagged += 1
        write_precheck_results(
            e.project_id, [*e.checks, finding, *item_findings.get(e.project_id, [])]
        )

    tally = {
        "extracted": len(extracted),
        "skipped": len(docs) - len(extracted),
        "yoy_flagged": yoy_flagged,
        "item_findings": sum(len(v) for v in item_findings.values()),
    }
    logger.info("structured-extraction summary: %s", tally)
    return tally


if __name__ == "__main__":
    extract_structured()
