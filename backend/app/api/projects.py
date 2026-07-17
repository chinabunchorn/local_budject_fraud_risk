"""Project list / drill-down / auditor feedback.

The drill-down serves the guardrails-validated `RiskResult` verbatim (re-parsed
through the shared contract) plus the deterministic Phase-F facts: bids,
prechecks, procurement fields. Feedback capture stores raw text; sentiment
stays NULL until the batch sentiment flow fills it (never scored live).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from schemas.risk import RiskResult
from sqlalchemy import select

from app.api.schemas import (
    BidOut,
    DocumentOut,
    FeedbackCreate,
    FeedbackOut,
    PrecheckFinding,
    ProjectDetail,
    ProjectListItem,
    ProjectListResponse,
    RiskResultOut,
    SubDistrictOut,
)
from app.core.dependencies import CurrentUser, SessionDep, get_current_user
from app.db import queries
from app.db.models import AuditorFeedbackRow, Project

router = APIRouter(prefix="/projects", tags=["projects"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    session: SessionDep,
    fiscal_year: int | None = None,
    sub_district_id: uuid.UUID | None = None,
    risk_level: str | None = None,
    q: str | None = None,
) -> ProjectListResponse:
    items = await queries.list_projects(
        session,
        fiscal_year=fiscal_year,
        sub_district_id=sub_district_id,
        risk_level=risk_level,
        q=q,
    )
    return ProjectListResponse(
        items=[
            ProjectListItem(
                id=i["project"].id,
                name_th=i["project"].name_th,
                fiscal_year=i["project"].fiscal_year,
                sub_district=SubDistrictOut.model_validate(i["project"].sub_district),
                budget_total=i["project"].budget_total,
                reference_price=i["project"].reference_price,
                contract_price=i["project"].contract_price,
                procurement_method=i["project"].procurement_method,
                risk_level=i["risk_level"],
                overall_score=i["overall_score"],
                precheck_flag_count=i["precheck_flag_count"],
            )
            for i in items
        ],
        total=len(items),
    )


@router.get("/{project_id}", response_model=ProjectDetail)
async def project_detail(project_id: uuid.UUID, session: SessionDep) -> ProjectDetail:
    data = await queries.get_project_detail(session, project_id)
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="ไม่พบโครงการ")
    project = data["project"]
    risk_row = data["risk"]
    precheck = data["precheck"]
    return ProjectDetail(
        id=project.id,
        name_th=project.name_th,
        fiscal_year=project.fiscal_year,
        category_th=project.category_th,
        status=project.status,
        sub_district=SubDistrictOut.model_validate(project.sub_district),
        budget_total=project.budget_total,
        reference_price=project.reference_price,
        contract_price=project.contract_price,
        procurement_method=project.procurement_method,
        bids=[BidOut.model_validate(b) for b in data["bids"]],
        documents=[DocumentOut.model_validate(d) for d in data["documents"]],
        prechecks=[
            PrecheckFinding.model_validate(c) for c in (precheck.checks if precheck else [])
        ],
        prechecks_generated_at=precheck.generated_at if precheck else None,
        risk=(
            RiskResultOut(
                result=RiskResult.model_validate(risk_row.result),
                validated_at=risk_row.validated_at,
            )
            if risk_row
            else None
        ),
    )


@router.get("/{project_id}/feedback", response_model=list[FeedbackOut])
async def list_feedback(project_id: uuid.UUID, session: SessionDep) -> list[FeedbackOut]:
    rows = (
        (
            await session.execute(
                select(AuditorFeedbackRow)
                .where(AuditorFeedbackRow.project_id == project_id)
                .order_by(AuditorFeedbackRow.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [FeedbackOut.model_validate(r, from_attributes=True) for r in rows]


@router.post(
    "/{project_id}/feedback",
    response_model=FeedbackOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_feedback(
    project_id: uuid.UUID,
    body: FeedbackCreate,
    session: SessionDep,
    user: CurrentUser,
) -> FeedbackOut:
    exists = (
        await session.execute(select(Project.id).where(Project.id == project_id))
    ).scalar_one_or_none()
    if exists is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="ไม่พบโครงการ")
    row = AuditorFeedbackRow(
        project_id=project_id,
        risk_result_id=body.risk_result_id,
        auditor_username=user.username,
        text_th=body.text_th,
        concern_tags=[],
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return FeedbackOut.model_validate(row, from_attributes=True)
