"""Portfolio overview + trend analytics — pre-computed data only (offline-first).

Both endpoints are Redis-cached (best effort) and read denormalized columns /
plain SQL window functions. No LLM call can occur on this path.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.schemas import (
    BudgetItemGroup,
    BudgetItemsResponse,
    BudgetReportGroup,
    BudgetReportTrendsResponse,
    BudgetReportYear,
    BudgetYearPoint,
    ContractorConcentration,
    HeatmapCell,
    ItemSource,
    ItemYear,
    OverviewResponse,
    OverviewTotals,
    PrecheckFinding,
    StandardPriceOut,
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


@router.get("/budget-report-trends", response_model=BudgetReportTrendsResponse)
async def budget_report_trends(session: SessionDep) -> BudgetReportTrendsResponse:
    """Multi-year budget totals summed from sub-district budget reports (shown
    on ภาพรวม). Deterministic; each year cites its source report PDF."""

    async def produce() -> dict:
        rows = await queries.budget_report_summaries(session)
        groups: dict[str, BudgetReportGroup] = {}
        for r in rows:
            sd_id = str(r["sub_district_id"])
            if sd_id not in groups:
                groups[sd_id] = BudgetReportGroup(
                    sub_district_id=r["sub_district_id"],
                    sub_district_name_th=r["sub_district_name_th"],
                    years=[],
                )
            groups[sd_id].years.append(
                BudgetReportYear(
                    fiscal_year=r["fiscal_year"],
                    total_budget=r["total_budget"],
                    project_count=r["project_count"],
                    budget_yoy_pct=r["budget_yoy_pct"],
                    document_id=r["document_id"],
                    document_filename=r["document_filename"],
                )
            )
        return BudgetReportTrendsResponse(items=list(groups.values())).model_dump(mode="json")

    return BudgetReportTrendsResponse.model_validate(
        await cached_json("dashboard:budget-report-trends", produce)
    )


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


@router.get("/budget-items", response_model=BudgetItemsResponse)
async def budget_items(session: SessionDep) -> BudgetItemsResponse:
    """Tracked-item unit-price series (quantities from budget reports, YoY via
    SQL window functions) + curated standard prices with citations + the
    item-level precheck findings. Deterministic data only."""

    async def produce() -> dict:
        data = await queries.budget_items(session)
        standards = {s["item_key"]: s for s in data["standards"]}
        findings_by_key: dict[str, list[dict]] = {}
        for f in data["findings"]:
            findings_by_key.setdefault(f["item_key"], []).append(f["finding"])

        groups: dict[tuple, BudgetItemGroup] = {}
        for r in data["rows"]:
            key = (str(r["sub_district_id"]), r["item_key"])
            std = standards.get(r["item_key"])
            if key not in groups:
                groups[key] = BudgetItemGroup(
                    item_key=r["item_key"],
                    label_th=(std["description_th"] if std else r["description_th"]),
                    sub_district_id=r["sub_district_id"],
                    sub_district_name_th=r["sub_district_name_th"],
                    years=[],
                    standard=(
                        StandardPriceOut(
                            description_th=std["description_th"],
                            standard_unit_price=std["standard_unit_price"],
                            fiscal_year=std["fiscal_year"],
                            provenance=std["provenance"],
                            document_id=std["source_document_id"],
                            filename=std["source_filename"],
                            page=std["source_page"],
                        )
                        if std
                        else None
                    ),
                    findings=[
                        PrecheckFinding.model_validate(f)
                        for f in findings_by_key.get(r["item_key"], [])
                    ],
                )
            unit_price = float(r["unit_price"]) if r["unit_price"] is not None else None
            pct_of_standard = (
                round(unit_price / float(std["standard_unit_price"]) * 100, 1)
                if std and unit_price is not None
                else None
            )
            groups[key].years.append(
                ItemYear(
                    fiscal_year=r["fiscal_year"],
                    project_id=r["project_id"],
                    project_name_th=r["project_name_th"],
                    quantity=r["quantity"],
                    unit_th=r["unit_th"],
                    total_amount=r["total_amount"],
                    unit_price=unit_price,
                    unit_price_yoy_pct=r["unit_price_yoy_pct"],
                    pct_of_standard=pct_of_standard,
                    winner_name=r["winner_name"],
                    bid_count=r["bid_count"],
                    procurement_method=r["procurement_method"],
                    source=ItemSource(
                        document_id=r["source_document_id"],
                        filename=r["source_filename"],
                        page=r["source_page"],
                        quote_th=r["source_quote_th"],
                    ),
                )
            )
        return BudgetItemsResponse(items=list(groups.values())).model_dump(mode="json")

    return BudgetItemsResponse.model_validate(
        await cached_json("dashboard:budget-items", produce)
    )
