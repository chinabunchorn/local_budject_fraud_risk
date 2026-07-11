"""Ingestion idempotency: content hash on documents, natural key on projects.

`documents.content_sha256` lets the ingestion flow skip unchanged files on
re-runs (the Phase-2 exit gate demands one-command idempotent re-processing).
The unique constraint on projects gives the corpus-manifest upsert a natural
conflict target.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-11
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("content_sha256", sa.Text))
    op.create_unique_constraint(
        "uq_projects_natural_key",
        "projects",
        ["sub_district_id", "name_th", "fiscal_year"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_projects_natural_key", "projects")
    op.drop_column("documents", "content_sha256")
