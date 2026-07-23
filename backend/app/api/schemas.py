"""API view models (request/response shapes) for the Phase 3 read API.

These are presentation shapes ONLY. The risk contract itself is never
redefined here — `schemas.RiskResult` (shared package) is served verbatim
after re-validation, and `schemas.Feedback` is extended, not duplicated.

Responsible-AI rule: every risk-bearing response carries `disclaimer_th` — the
system flags, the human auditor decides. No banned lexicon in any copy here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from schemas.feedback import Feedback
from schemas.risk import RiskResult

# Shown on every risk-bearing surface. "แจ้งจุดที่ควรตรวจสอบ ไม่ชี้ข้อสรุป" —
# flags points to review, never states conclusions.
DISCLAIMER_TH = (
    "ผลการวิเคราะห์นี้เป็นการแจ้งจุดที่ควรตรวจสอบเพิ่มเติมจากระบบช่วยวิเคราะห์เท่านั้น "
    "ไม่ใช่ข้อสรุปหรือคำตัดสินใด ๆ ผู้ตรวจสอบเป็นผู้พิจารณาและตัดสินใจขั้นสุดท้าย"
)

# Display order/severity of the closed verdict enum (REQUIRES_INVESTIGATION first)
RISK_LEVEL_RANK: dict[str, int] = {
    "REQUIRES_INVESTIGATION": 4,
    "HIGH": 3,
    "MEDIUM": 2,
    "LOW": 1,
}
_RANK_TO_LEVEL = {v: k for k, v in RISK_LEVEL_RANK.items()}


def rank_to_level(rank: int | None) -> str | None:
    return _RANK_TO_LEVEL.get(rank) if rank is not None else None


# ---- auth ---------------------------------------------------------------------


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    username: str
    display_name_th: str
    role: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int
    user: UserOut


# ---- projects -----------------------------------------------------------------


class SubDistrictOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name_th: str
    district_th: str
    province_th: str


class BidOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    bidder_name_th: str
    bid_amount: float
    is_winner: bool


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    doc_type: str | None
    scope: str
    source: str
    parse_status: str
    page_count: int | None


class PrecheckFinding(BaseModel):
    """Mirror of pipelines/common/prechecks.py `_finding` — the pipeline owns
    this shape; extra keys (e.g. `severity` on YoY findings) pass through."""

    model_config = ConfigDict(extra="allow")

    name: str
    status: str
    detail: str
    values: dict[str, Any] = Field(default_factory=dict)


class RiskResultOut(BaseModel):
    """The full shared contract plus storage provenance."""

    result: RiskResult
    validated_at: datetime


class ProjectListItem(BaseModel):
    id: UUID
    name_th: str
    fiscal_year: int
    sub_district: SubDistrictOut
    budget_total: float | None
    reference_price: float | None
    contract_price: float | None
    procurement_method: str | None
    risk_level: str | None
    overall_score: float | None
    precheck_flag_count: int


class ProjectListResponse(BaseModel):
    items: list[ProjectListItem]
    total: int
    disclaimer_th: str = DISCLAIMER_TH


class ProjectDetail(BaseModel):
    id: UUID
    name_th: str
    fiscal_year: int
    category_th: str | None
    status: str
    sub_district: SubDistrictOut
    budget_total: float | None
    reference_price: float | None
    contract_price: float | None
    procurement_method: str | None
    bids: list[BidOut]
    documents: list[DocumentOut]
    prechecks: list[PrecheckFinding]
    prechecks_generated_at: datetime | None
    risk: RiskResultOut | None
    disclaimer_th: str = DISCLAIMER_TH


# ---- feedback -----------------------------------------------------------------


class FeedbackCreate(BaseModel):
    text_th: str = Field(min_length=1)
    risk_result_id: UUID | None = None


class FeedbackOut(Feedback):
    auditor_username: str


# ---- citations / regulations --------------------------------------------------


class ChunkOut(BaseModel):
    """Citation resolution target: the retrieved passage plus its document."""

    id: UUID
    document_id: UUID
    chunk_index: int
    text: str
    page: int | None
    language: str
    document: DocumentOut


class RegulationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    regulation_code: str
    act_name_th: str
    section_no: str
    section_title_th: str | None
    text: str


# ---- dashboard ----------------------------------------------------------------


class OverviewTotals(BaseModel):
    project_count: int
    sub_district_count: int
    document_count: int
    budget_total_sum: float
    scored_project_count: int


class HeatmapCell(BaseModel):
    sub_district_id: UUID
    sub_district_name_th: str
    fiscal_year: int
    project_count: int
    budget_total: float | None
    avg_score: float | None
    worst_risk_level: str | None


class TopProject(BaseModel):
    id: UUID
    name_th: str
    sub_district_name_th: str
    fiscal_year: int
    risk_level: str
    overall_score: float


class OverviewResponse(BaseModel):
    totals: OverviewTotals
    # keys are the closed RiskLevel enum values
    risk_distribution: dict[str, int]
    heatmap: list[HeatmapCell]
    top_projects: list[TopProject]
    disclaimer_th: str = DISCLAIMER_TH


class BudgetYearPoint(BaseModel):
    sub_district_id: UUID
    sub_district_name_th: str
    fiscal_year: int
    project_count: int
    budget_total: float | None
    yoy_pct: float | None


class ContractorConcentration(BaseModel):
    bidder_name_th: str
    bids_submitted: int
    contracts_won: int
    total_awarded: float | None
    awarded_share_pct: float | None
    fiscal_years: list[int]


class TrendsResponse(BaseModel):
    budget_by_year: list[BudgetYearPoint]
    contractor_concentration: list[ContractorConcentration]
    disclaimer_th: str = DISCLAIMER_TH


# ---- budget items (tracked-item anomaly page) ----------------------------------


class ItemSource(BaseModel):
    """Where the quantity/total came from — opens in the PDF viewer."""

    document_id: UUID | None
    filename: str | None
    page: int | None
    quote_th: str | None


class ItemYear(BaseModel):
    fiscal_year: int
    project_id: UUID
    project_name_th: str
    quantity: float
    unit_th: str | None
    total_amount: float
    unit_price: float | None
    unit_price_yoy_pct: float | None
    pct_of_standard: float | None
    winner_name: str | None
    bid_count: int
    procurement_method: str | None
    source: ItemSource


class StandardPriceOut(BaseModel):
    """Curated reference price with its citation — provenance is shown to the
    auditor, never hidden."""

    description_th: str
    standard_unit_price: float
    fiscal_year: int | None
    provenance: str
    document_id: UUID | None
    filename: str | None
    page: int | None


class BudgetItemGroup(BaseModel):
    item_key: str
    label_th: str
    sub_district_id: UUID
    sub_district_name_th: str
    years: list[ItemYear]
    standard: StandardPriceOut | None
    findings: list[PrecheckFinding]


class BudgetItemsResponse(BaseModel):
    items: list[BudgetItemGroup]
    disclaimer_th: str = DISCLAIMER_TH


# ---- budget-report trends (ภาพรวม budget-by-year chart) -------------------------


class BudgetTopItem(BaseModel):
    description_th: str
    amount: float


class BudgetReportYear(BaseModel):
    fiscal_year: int
    total_budget: float
    project_count: int
    budget_yoy_pct: float | None
    top_items: list[BudgetTopItem]
    document_id: UUID | None
    document_filename: str | None


class BudgetReportGroup(BaseModel):
    sub_district_id: UUID
    sub_district_name_th: str
    years: list[BudgetReportYear]


class BudgetReportTrendsResponse(BaseModel):
    items: list[BudgetReportGroup]
    disclaimer_th: str = DISCLAIMER_TH


# ---- chat (Phase 4 live RAG) --------------------------------------------------


class ChatMessageIn(BaseModel):
    """A prior conversation turn replayed by the frontend (stateless backend)."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2000)
    history: list[ChatMessageIn] = Field(default_factory=list)
    # Optional, bounded per-request overrides of the two measured optimization
    # levers, so the benchmark harness can A/B configs against one running
    # backend. Absent in normal use (settings defaults apply).
    rerank_top_n: int | None = Field(default=None, ge=1, le=20)
    max_tokens: int | None = Field(default=None, ge=64, le=2048)
