"""Item-level procurement facts for unit-price anomaly tracking.

`project_items`: one row per tracked line item of a project, extracted
100% deterministically from budget-report lines (quantity + total → unit
price as a generated column). Every row carries its source document, page,
and the exact quoted line — evidence-first, never invented.

`standard_prices`: reference unit prices (ราคามาตรฐานครุภัณฑ์ etc.). The
source books are scans (NEEDS_OCR by standing decision), so rows are CURATED
by the data team, each citing the reference document + page the auditor can
open in the PDF viewer. `provenance` records that honestly; EXTRACTED becomes
possible after a future OCR pass.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-22
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_items",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # normalized identity for cross-year matching, e.g. "water-tank-plastic-2000l"
        sa.Column("item_key", sa.Text, nullable=False),
        sa.Column("description_th", sa.Text, nullable=False),
        sa.Column("quantity", sa.Numeric(12, 2), nullable=False),
        sa.Column("unit_th", sa.Text),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "unit_price",
            sa.Numeric(14, 2),
            sa.Computed("total_amount / NULLIF(quantity, 0)", persisted=True),
        ),
        sa.Column(
            "source_document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
        ),
        sa.Column("source_page", sa.Integer),
        sa.Column("source_quote_th", sa.Text),
        sa.Column(
            "extracted_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("quantity > 0", name="ck_project_items_quantity"),
        sa.UniqueConstraint("project_id", "item_key"),
    )
    op.create_index("ix_project_items_project", "project_items", ["project_id"])
    op.create_index("ix_project_items_key", "project_items", ["item_key"])

    op.create_table(
        "standard_prices",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("item_key", sa.Text, nullable=False, unique=True),
        sa.Column("description_th", sa.Text, nullable=False),
        sa.Column("standard_unit_price", sa.Numeric(14, 2), nullable=False),
        # edition year of the standard book, พ.ศ., when known
        sa.Column("fiscal_year", sa.SmallInteger),
        sa.Column(
            "source_document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
        ),
        sa.Column("source_page", sa.Integer),
        sa.Column("provenance", sa.Text, nullable=False, server_default="CURATED"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "provenance IN ('CURATED', 'EXTRACTED')", name="ck_standard_prices_provenance"
        ),
        sa.CheckConstraint("standard_unit_price > 0", name="ck_standard_prices_positive"),
    )


def downgrade() -> None:
    op.drop_table("standard_prices")
    op.drop_table("project_items")
