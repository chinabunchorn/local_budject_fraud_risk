"""Shape the schema for the real corpus (see docs/DATA_TEAM_GUIDE.md).

- documents gain a scope: PROJECT docs belong to a project (as before);
  SUB_DISTRICT docs are the per-sub-district budget reports (รายงานงบประมาณ);
  REFERENCE docs are the central standard-price tables (เอกสารกลาง).
  project_id therefore becomes nullable, with a consistency check.
- projects gain procurement facts extracted from บก.01 / contract summaries:
  method (the 500k-threshold e-Bidding vs เฉพาะเจาะจง route), reference_price
  (ราคากลาง baseline), contract_price (winning bid). budget_total becomes
  nullable — real totals are extracted from documents, never invented.
- bids: one row per bidder per project from บก.06 — powers bid-rigging and
  %-competition analytics as plain SQL (no LLM in that path).

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-12
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("scope", sa.Text, nullable=False, server_default="PROJECT"),
    )
    op.add_column(
        "documents",
        sa.Column(
            "sub_district_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sub_districts.id", ondelete="CASCADE"),
        ),
    )
    op.alter_column("documents", "project_id", nullable=True)
    op.create_check_constraint(
        "ck_documents_scope",
        "documents",
        "scope IN ('PROJECT', 'SUB_DISTRICT', 'REFERENCE')",
    )
    op.create_check_constraint(
        "ck_documents_scope_owner",
        "documents",
        "(scope = 'PROJECT' AND project_id IS NOT NULL) OR "
        "(scope = 'SUB_DISTRICT' AND sub_district_id IS NOT NULL AND project_id IS NULL) OR "
        "(scope = 'REFERENCE' AND project_id IS NULL AND sub_district_id IS NULL)",
    )

    op.alter_column("projects", "budget_total", nullable=True)
    op.add_column("projects", sa.Column("procurement_method", sa.Text))
    op.add_column("projects", sa.Column("reference_price", sa.Numeric(14, 2)))
    op.add_column("projects", sa.Column("contract_price", sa.Numeric(14, 2)))
    op.create_check_constraint(
        "ck_projects_procurement_method",
        "projects",
        "procurement_method IS NULL OR "
        "procurement_method IN ('E_BIDDING', 'SELECTION', 'SPECIFIC')",
    )

    op.create_table(
        "bids",
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
        sa.Column("bidder_name_th", sa.Text, nullable=False),
        sa.Column("bid_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("is_winner", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("project_id", "bidder_name_th"),
    )
    op.create_index("ix_bids_project", "bids", ["project_id"])
    op.create_index("ix_bids_bidder", "bids", ["bidder_name_th"])


def downgrade() -> None:
    op.drop_table("bids")
    op.drop_constraint("ck_projects_procurement_method", "projects")
    op.drop_column("projects", "contract_price")
    op.drop_column("projects", "reference_price")
    op.drop_column("projects", "procurement_method")
    op.alter_column("projects", "budget_total", nullable=False)
    op.drop_constraint("ck_documents_scope_owner", "documents")
    op.drop_constraint("ck_documents_scope", "documents")
    op.alter_column("documents", "project_id", nullable=False)
    op.drop_column("documents", "sub_district_id")
    op.drop_column("documents", "scope")
