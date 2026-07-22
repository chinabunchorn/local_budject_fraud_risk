"""Deterministic pre-check results (Phase F structured extraction).

The structured-extraction flow writes accounting facts pulled from documents by
100% deterministic code — never an LLM — into `projects` (budget_total,
reference_price, contract_price, procurement_method), `bids` (from the
contract-summary bidder/winner tables), and this table.

`precheck_results.checks` is a JSONB array of factual, non-accusatory findings
(BOQ↔บก.01 sum, ราคากลาง cross-check, bid competition, 500k-threshold
proximity, expected-documents-per-route). It is the deterministic evidence the
Phase-G score_risk flow feeds to the model — the arithmetic is settled here so
the LLM never does it. One row per project (idempotent upsert).

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-13
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "precheck_results",
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
            unique=True,
        ),
        # array of {name, status, detail, values} findings — see common/prechecks.py
        sa.Column("checks", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column(
            "generated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_precheck_results_project", "precheck_results", ["project_id"])


def downgrade() -> None:
    op.drop_table("precheck_results")
