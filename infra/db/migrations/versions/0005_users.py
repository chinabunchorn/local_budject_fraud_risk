"""Users for the dashboard's simple JWT RBAC (Phase 3).

Three fixed roles — ADMIN > SENIOR_AUDITOR > AUDITOR — checked in the backend;
Keycloak remains a documented upgrade path, so this table is deliberately
minimal. Passwords are bcrypt hashes written by backend/scripts/seed_users.py;
nothing in this repo ever stores a plaintext password.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-17
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("username", sa.Text, nullable=False, unique=True),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("display_name_th", sa.Text, nullable=False),
        sa.Column("role", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "role IN ('ADMIN', 'SENIOR_AUDITOR', 'AUDITOR')", name="ck_users_role"
        ),
    )


def downgrade() -> None:
    op.drop_table("users")
