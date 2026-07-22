"""Read-side ORM mapping of the existing schema (migrations 0001–0005).

The schema is owned by infra/db migrations — these classes only mirror the
columns the API reads. Embedding vector columns are deliberately NOT mapped:
the dashboard never touches them, and leaving them out keeps pgvector out of
the backend's dependencies. `risk_results.result` holds a guardrails-validated
`schemas.RiskResult` payload; the API re-parses it through the shared contract
before serving.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    type_annotation_map = {
        uuid.UUID: UUID(as_uuid=True),
        dict[str, Any]: JSONB,
        list[Any]: JSONB,
        str: Text,
    }


class SubDistrict(Base):
    __tablename__ = "sub_districts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    name_th: Mapped[str]
    district_th: Mapped[str]
    province_th: Mapped[str]
    created_at: Mapped[datetime]


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    sub_district_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sub_districts.id"))
    name_th: Mapped[str]
    fiscal_year: Mapped[int]
    category_th: Mapped[str | None]
    budget_total: Mapped[Decimal | None]
    status: Mapped[str]
    procurement_method: Mapped[str | None]
    reference_price: Mapped[Decimal | None]
    contract_price: Mapped[Decimal | None]
    created_at: Mapped[datetime]

    sub_district: Mapped[SubDistrict] = relationship(lazy="joined")


class BudgetLine(Base):
    __tablename__ = "budget_lines"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    line_no: Mapped[int]
    description_th: Mapped[str]
    amount: Mapped[Decimal]
    vendor_name_th: Mapped[str | None]
    transaction_date: Mapped[date | None]


class Bid(Base):
    __tablename__ = "bids"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    bidder_name_th: Mapped[str]
    bid_amount: Mapped[Decimal]
    is_winner: Mapped[bool]


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"))
    sub_district_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sub_districts.id"))
    scope: Mapped[str]
    minio_key: Mapped[str]
    filename: Mapped[str]
    doc_type: Mapped[str | None]
    source: Mapped[str]
    parse_status: Mapped[str]
    page_count: Mapped[int | None]
    created_at: Mapped[datetime]


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"))
    chunk_index: Mapped[int]
    text: Mapped[str]
    page: Mapped[int | None]
    language: Mapped[str]
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB)

    document: Mapped[Document] = relationship(lazy="joined")


class ProjectItem(Base):
    """Tracked line item (migration 0006): quantity from the budget report,
    unit_price is a DB-generated column (total / quantity)."""

    __tablename__ = "project_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    item_key: Mapped[str]
    description_th: Mapped[str]
    quantity: Mapped[Decimal]
    unit_th: Mapped[str | None]
    total_amount: Mapped[Decimal]
    unit_price: Mapped[Decimal | None]
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id"))
    source_page: Mapped[int | None]
    source_quote_th: Mapped[str | None]
    extracted_at: Mapped[datetime]


class StandardPrice(Base):
    """Curated reference unit price (migration 0006), citing the scanned
    standard-price book so the auditor can verify the number in the viewer."""

    __tablename__ = "standard_prices"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    item_key: Mapped[str]
    description_th: Mapped[str]
    standard_unit_price: Mapped[Decimal]
    fiscal_year: Mapped[int | None]
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id"))
    source_page: Mapped[int | None]
    provenance: Mapped[str]
    created_at: Mapped[datetime]


class Regulation(Base):
    __tablename__ = "regulations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    regulation_code: Mapped[str]
    act_name_th: Mapped[str]
    section_no: Mapped[str]
    section_title_th: Mapped[str | None]
    text: Mapped[str]


class RiskResultRow(Base):
    __tablename__ = "risk_results"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    result: Mapped[dict[str, Any]] = mapped_column(JSONB)
    risk_level: Mapped[str]
    overall_score: Mapped[Decimal]
    model_id: Mapped[str]
    prompt_version: Mapped[str]
    generated_at: Mapped[datetime]
    validated_at: Mapped[datetime]


class PrecheckResultRow(Base):
    __tablename__ = "precheck_results"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    checks: Mapped[list[Any]] = mapped_column(JSONB)
    generated_at: Mapped[datetime]


class AuditorFeedbackRow(Base):
    """The one table this API writes — declare the server defaults so ORM
    inserts omit id/created_at and let PostgreSQL fill them."""

    __tablename__ = "auditor_feedback"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    risk_result_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("risk_results.id"))
    auditor_username: Mapped[str]
    text_th: Mapped[str]
    sentiment: Mapped[str | None]
    concern_tags: Mapped[list[Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    username: Mapped[str]
    password_hash: Mapped[str]
    display_name_th: Mapped[str]
    role: Mapped[str]
    is_active: Mapped[bool]
    created_at: Mapped[datetime]
