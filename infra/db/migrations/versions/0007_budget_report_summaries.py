"""Per-year budget totals summed from sub-district budget reports.

Deterministic (no LLM): the budget reports (รายงานงบประมาณ) are line-item
project tables; `flows/extract_budget_summaries.py` sums the amount column and
counts the rows per report, writing one row per (sub_district, fiscal_year)
here. `document_id` cites the source report so the ภาพรวม chart can open the
real PDF at the summed page.

Scope note: only sub-districts whose reports are genuine line-item budget
tables are summarized (Tambon Hua Khao). Tambon Tha Chang's reports are
narrative policy / audit-disclosure documents, not budget tables, so they are
deliberately NOT summed here (would need curated entry instead).

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "budget_report_summaries",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "sub_district_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sub_districts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fiscal_year", sa.SmallInteger, nullable=False),  # พ.ศ.
        sa.Column(
            "document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
        ),
        sa.Column("total_budget", sa.Numeric(16, 2), nullable=False),
        sa.Column("project_count", sa.Integer, nullable=False),
        sa.Column(
            "extracted_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("total_budget >= 0", name="ck_budget_report_summaries_total"),
        sa.CheckConstraint("project_count >= 0", name="ck_budget_report_summaries_count"),
        sa.UniqueConstraint("sub_district_id", "fiscal_year"),
    )
    op.create_index(
        "ix_budget_report_summaries_sd", "budget_report_summaries", ["sub_district_id"]
    )


def downgrade() -> None:
    op.drop_table("budget_report_summaries")
