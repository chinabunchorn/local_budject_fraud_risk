"""Read queries for the dashboard. Trend/aggregate analytics are plain SQL
(window functions) per the architectural rule — no LLM anywhere in this path.

"Latest risk per project" = most recent `validated_at` row; the unique key
(project_id, prompt_version, model_id) allows multiple runs to coexist.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.schemas import RISK_LEVEL_RANK
from app.db.models import (
    Bid,
    Chunk,
    Document,
    PrecheckResultRow,
    Project,
    Regulation,
    RiskResultRow,
)

_LEVEL_RANK_SQL = (
    "CASE l.risk_level WHEN 'REQUIRES_INVESTIGATION' THEN 4 WHEN 'HIGH' THEN 3 "
    "WHEN 'MEDIUM' THEN 2 WHEN 'LOW' THEN 1 END"
)

_LATEST_RISK_CTE = """
    latest AS (
        SELECT DISTINCT ON (project_id)
               project_id, risk_level, overall_score, validated_at
        FROM risk_results
        ORDER BY project_id, validated_at DESC
    )
"""


def latest_risk_subquery():
    return (
        select(
            RiskResultRow.project_id,
            RiskResultRow.risk_level,
            RiskResultRow.overall_score,
        )
        .distinct(RiskResultRow.project_id)
        .order_by(RiskResultRow.project_id, RiskResultRow.validated_at.desc())
        .subquery()
    )


async def list_projects(
    session: AsyncSession,
    *,
    fiscal_year: int | None = None,
    sub_district_id: uuid.UUID | None = None,
    risk_level: str | None = None,
    q: str | None = None,
) -> list[dict[str, Any]]:
    latest = latest_risk_subquery()
    stmt = (
        select(Project, latest.c.risk_level, latest.c.overall_score, PrecheckResultRow.checks)
        .outerjoin(latest, latest.c.project_id == Project.id)
        .outerjoin(PrecheckResultRow, PrecheckResultRow.project_id == Project.id)
    )
    if fiscal_year is not None:
        stmt = stmt.where(Project.fiscal_year == fiscal_year)
    if sub_district_id is not None:
        stmt = stmt.where(Project.sub_district_id == sub_district_id)
    if risk_level is not None:
        stmt = stmt.where(latest.c.risk_level == risk_level)
    if q:
        stmt = stmt.where(Project.name_th.ilike(f"%{q}%"))

    rows = (await session.execute(stmt)).all()
    items = [
        {
            "project": project,
            "risk_level": level,
            "overall_score": score,
            "precheck_flag_count": sum(
                1 for c in (checks or []) if c.get("status") == "FLAG"
            ),
        }
        for project, level, score, checks in rows
    ]
    # Severity first (REQUIRES_INVESTIGATION on top), then score, then year desc
    items.sort(
        key=lambda i: (
            RISK_LEVEL_RANK.get(i["risk_level"] or "", 0),
            i["overall_score"] or 0,
            i["project"].fiscal_year,
        ),
        reverse=True,
    )
    return items


async def get_project_detail(
    session: AsyncSession, project_id: uuid.UUID
) -> dict[str, Any] | None:
    project = (
        await session.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if project is None:
        return None

    bids = (
        (
            await session.execute(
                select(Bid)
                .where(Bid.project_id == project_id)
                .order_by(Bid.is_winner.desc(), Bid.bid_amount)
            )
        )
        .scalars()
        .all()
    )
    documents = (
        (
            await session.execute(
                select(Document)
                .where(Document.project_id == project_id)
                .order_by(Document.filename)
            )
        )
        .scalars()
        .all()
    )
    precheck = (
        await session.execute(
            select(PrecheckResultRow).where(PrecheckResultRow.project_id == project_id)
        )
    ).scalar_one_or_none()
    risk = (
        await session.execute(
            select(RiskResultRow)
            .where(RiskResultRow.project_id == project_id)
            .order_by(RiskResultRow.validated_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    return {
        "project": project,
        "bids": bids,
        "documents": documents,
        "precheck": precheck,
        "risk": risk,
    }


async def get_chunk(session: AsyncSession, chunk_id: uuid.UUID) -> Chunk | None:
    return (
        await session.execute(
            select(Chunk)
            .options(selectinload(Chunk.document))
            .where(Chunk.id == chunk_id)
        )
    ).scalar_one_or_none()


async def get_regulation(session: AsyncSession, regulation_code: str) -> Regulation | None:
    return (
        await session.execute(
            select(Regulation).where(Regulation.regulation_code == regulation_code)
        )
    ).scalar_one_or_none()


async def portfolio_overview(session: AsyncSession) -> dict[str, Any]:
    totals = (
        await session.execute(
            text(
                """
                SELECT
                  (SELECT count(*) FROM projects) AS project_count,
                  (SELECT count(*) FROM sub_districts) AS sub_district_count,
                  (SELECT count(*) FROM documents) AS document_count,
                  (SELECT coalesce(sum(coalesce(budget_total, contract_price)), 0)
                     FROM projects) AS budget_total_sum,
                  (SELECT count(DISTINCT project_id) FROM risk_results)
                     AS scored_project_count
                """
            )
        )
    ).mappings().one()

    distribution_rows = (
        await session.execute(
            text(
                f"WITH {_LATEST_RISK_CTE} "
                "SELECT risk_level, count(*) AS n FROM latest GROUP BY risk_level"
            )
        )
    ).mappings().all()

    heatmap_rows = (
        await session.execute(
            text(
                f"""
                WITH {_LATEST_RISK_CTE}
                SELECT sd.id AS sub_district_id,
                       sd.name_th AS sub_district_name_th,
                       p.fiscal_year,
                       count(*) AS project_count,
                       sum(coalesce(p.budget_total, p.contract_price)) AS budget_total,
                       round(avg(l.overall_score), 1) AS avg_score,
                       max({_LEVEL_RANK_SQL}) AS worst_rank
                FROM projects p
                JOIN sub_districts sd ON sd.id = p.sub_district_id
                LEFT JOIN latest l ON l.project_id = p.id
                GROUP BY sd.id, sd.name_th, p.fiscal_year
                ORDER BY sd.name_th, p.fiscal_year
                """
            )
        )
    ).mappings().all()

    top_rows = (
        await session.execute(
            text(
                f"""
                WITH {_LATEST_RISK_CTE}
                SELECT p.id, p.name_th, sd.name_th AS sub_district_name_th,
                       p.fiscal_year, l.risk_level, l.overall_score
                FROM latest l
                JOIN projects p ON p.id = l.project_id
                JOIN sub_districts sd ON sd.id = p.sub_district_id
                ORDER BY {_LEVEL_RANK_SQL} DESC, l.overall_score DESC
                LIMIT 5
                """
            )
        )
    ).mappings().all()

    return {
        "totals": dict(totals),
        "distribution": {r["risk_level"]: r["n"] for r in distribution_rows},
        "heatmap": [dict(r) for r in heatmap_rows],
        "top_projects": [dict(r) for r in top_rows],
    }


async def trends(session: AsyncSession) -> dict[str, Any]:
    budget_rows = (
        await session.execute(
            text(
                """
                WITH yearly AS (
                    SELECT p.sub_district_id,
                           sd.name_th AS sub_district_name_th,
                           p.fiscal_year,
                           count(*) AS project_count,
                           sum(coalesce(p.budget_total, p.contract_price)) AS budget_total
                    FROM projects p
                    JOIN sub_districts sd ON sd.id = p.sub_district_id
                    GROUP BY p.sub_district_id, sd.name_th, p.fiscal_year
                )
                SELECT *,
                       round(
                         100.0 * (budget_total - lag(budget_total) OVER w)
                               / nullif(lag(budget_total) OVER w, 0),
                         1
                       ) AS yoy_pct
                FROM yearly
                WINDOW w AS (PARTITION BY sub_district_id ORDER BY fiscal_year)
                ORDER BY sub_district_name_th, fiscal_year
                """
            )
        )
    ).mappings().all()

    contractor_rows = (
        await session.execute(
            text(
                """
                SELECT b.bidder_name_th,
                       count(*) AS bids_submitted,
                       count(*) FILTER (WHERE b.is_winner) AS contracts_won,
                       sum(b.bid_amount) FILTER (WHERE b.is_winner) AS total_awarded,
                       round(
                         100.0 * sum(b.bid_amount) FILTER (WHERE b.is_winner)
                               / nullif(sum(sum(b.bid_amount) FILTER (WHERE b.is_winner))
                                          OVER (), 0),
                         1
                       ) AS awarded_share_pct,
                       array_agg(DISTINCT p.fiscal_year) AS fiscal_years
                FROM bids b
                JOIN projects p ON p.id = b.project_id
                GROUP BY b.bidder_name_th
                ORDER BY total_awarded DESC NULLS LAST, contracts_won DESC
                """
            )
        )
    ).mappings().all()

    return {
        "budget_by_year": [dict(r) for r in budget_rows],
        "contractor_concentration": [dict(r) for r in contractor_rows],
    }
