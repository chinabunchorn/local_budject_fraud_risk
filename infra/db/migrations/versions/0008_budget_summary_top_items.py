"""Top-N highest-budget line items per budget-report summary.

Adds `top_items` to `budget_report_summaries`: a JSONB array of the highest
line items in the report, sorted by amount descending —
[{"description_th": ..., "amount": "..."}] — written by
`flows/extract_budget_summaries.py`. Powers the "Top 3 highest-budget
projects" table beside the ภาพรวม budget-trend chart. Deterministic, no LLM.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "budget_report_summaries",
        sa.Column(
            "top_items", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
    )


def downgrade() -> None:
    op.drop_column("budget_report_summaries", "top_items")
