"""Portfolio overview + trend analytics — pre-computed data only (offline-first).

Both endpoints are Redis-cached (best effort) and read denormalized columns /
plain SQL window functions. No LLM call can occur on this path.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.schemas import (
    BudgetYearPoint,
    ContractorConcentration,
    HeatmapCell,
    OverviewResponse,
    OverviewTotals,
    TopProject,
    TrendsResponse,
    rank_to_level,
)
from app.core.dependencies import SessionDep, get_current_user
from app.db import queries
from app.services.cache import cached_json

router = APIRouter(
    prefix="/dashboard", tags=["dashboard"], dependencies=[Depends(get_current_user)]
)


@router.get("/overview", response_model=OverviewResponse)
async def overview(session: SessionDep) -> OverviewResponse:
    async def produce() -> dict:
        data = await queries.portfolio_overview(session)
        return OverviewResponse(
            totals=OverviewTotals(**data["totals"]),
            risk_distribution=data["distribution"],
            heatmap=[
                HeatmapCell(
                    **{k: v for k, v in row.items() if k != "worst_rank"},
                    worst_risk_level=rank_to_level(row["worst_rank"]),
                )
                for row in data["heatmap"]
            ],
            top_projects=[TopProject(**row) for row in data["top_projects"]],
        ).model_dump(mode="json")

    return OverviewResponse.model_validate(await cached_json("dashboard:overview", produce))


@router.get("/trends", response_model=TrendsResponse)
async def trends(session: SessionDep) -> TrendsResponse:
    async def produce() -> dict:
        data = await queries.trends(session)
        return TrendsResponse(
            budget_by_year=[BudgetYearPoint(**row) for row in data["budget_by_year"]],
            contractor_concentration=[
                ContractorConcentration(**row) for row in data["contractor_concentration"]
            ],
        ).model_dump(mode="json")

    return TrendsResponse.model_validate(await cached_json("dashboard:trends", produce))
