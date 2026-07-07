"""Initial schema: sub_districts, projects, budget_lines, documents,
chunks (pgvector), regulations, risk_results (JSONB), auditor_feedback.

The `risk_results.result` JSONB column stores a guardrails-validated
`schemas.RiskResult`; `risk_level` / `overall_score` are denormalized copies
for plain-SQL dashboard and trend queries (no LLM in that path).
Embedding columns are vector(1024) to match BGE-M3 (schemas.EMBEDDING_DIM).

Revision ID: 0001
Revises:
Create Date: 2026-07-06
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

EMBEDDING_DIM = 1024  # keep in sync with schemas.EMBEDDING_DIM

RISK_LEVELS = ("LOW", "MEDIUM", "HIGH", "REQUIRES_INVESTIGATION")
SENTIMENTS = ("POSITIVE", "NEUTRAL", "NEGATIVE")


def _uuid_pk() -> sa.Column:
    return sa.Column(
        "id",
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "sub_districts",
        _uuid_pk(),
        sa.Column("name_th", sa.Text, nullable=False),
        sa.Column("district_th", sa.Text, nullable=False),
        sa.Column("province_th", sa.Text, nullable=False),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("name_th", "district_th", "province_th"),
    )

    op.create_table(
        "projects",
        _uuid_pk(),
        sa.Column(
            "sub_district_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sub_districts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name_th", sa.Text, nullable=False),
        sa.Column("fiscal_year", sa.SmallInteger, nullable=False),  # พ.ศ., e.g. 2567
        sa.Column("category_th", sa.Text),
        sa.Column("budget_total", sa.Numeric(14, 2), nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="ACTIVE"),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_projects_sub_district", "projects", ["sub_district_id"])
    op.create_index("ix_projects_fiscal_year", "projects", ["fiscal_year"])

    op.create_table(
        "budget_lines",
        _uuid_pk(),
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("line_no", sa.Integer, nullable=False),
        sa.Column("description_th", sa.Text, nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("vendor_name_th", sa.Text),
        sa.Column("transaction_date", sa.Date),
        sa.UniqueConstraint("project_id", "line_no"),
    )
    op.create_index("ix_budget_lines_project", "budget_lines", ["project_id"])
    op.create_index("ix_budget_lines_vendor", "budget_lines", ["vendor_name_th"])
    op.create_index("ix_budget_lines_date", "budget_lines", ["transaction_date"])

    op.create_table(
        "documents",
        _uuid_pk(),
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("minio_key", sa.Text, nullable=False, unique=True),
        sa.Column("filename", sa.Text, nullable=False),
        sa.Column("doc_type", sa.Text),  # e.g. contract, invoice, project_sheet
        sa.Column("source", sa.Text, nullable=False, server_default="BORN_DIGITAL"),
        sa.Column("parse_status", sa.Text, nullable=False, server_default="PENDING"),
        sa.Column("page_count", sa.Integer),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("source IN ('BORN_DIGITAL', 'SCANNED')", name="ck_documents_source"),
    )
    op.create_index("ix_documents_project", "documents", ["project_id"])

    op.create_table(
        "chunks",
        _uuid_pk(),
        sa.Column(
            "document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("page", sa.Integer),
        sa.Column("language", sa.Text, nullable=False, server_default="th"),
        sa.Column("metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("embedding", Vector(EMBEDDING_DIM)),
        sa.UniqueConstraint("document_id", "chunk_index"),
    )
    op.create_index("ix_chunks_document", "chunks", ["document_id"])
    op.create_index(
        "ix_chunks_embedding_hnsw",
        "chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.create_table(
        "regulations",
        _uuid_pk(),
        # e.g. "fiscal-discipline-act-2561/s.37" — RegulationReference.regulation_id resolves here
        sa.Column("regulation_code", sa.Text, nullable=False, unique=True),
        sa.Column("act_name_th", sa.Text, nullable=False),
        sa.Column("section_no", sa.Text, nullable=False),
        sa.Column("section_title_th", sa.Text),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM)),
    )
    op.create_index(
        "ix_regulations_embedding_hnsw",
        "regulations",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.create_table(
        "risk_results",
        _uuid_pk(),
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Full guardrails-validated schemas.RiskResult payload
        sa.Column("result", JSONB, nullable=False),
        # Denormalized for SQL dashboards / trend queries
        sa.Column("risk_level", sa.Text, nullable=False),
        sa.Column("overall_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("model_id", sa.Text, nullable=False),
        sa.Column("prompt_version", sa.Text, nullable=False),
        sa.Column("generated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "validated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'REQUIRES_INVESTIGATION')",
            name="ck_risk_results_level",
        ),
        sa.CheckConstraint(
            "overall_score >= 0 AND overall_score <= 100", name="ck_risk_results_score"
        ),
        # Idempotent batch re-runs upsert on this key
        sa.UniqueConstraint("project_id", "prompt_version", "model_id"),
    )
    op.create_index("ix_risk_results_project", "risk_results", ["project_id"])
    op.create_index("ix_risk_results_level", "risk_results", ["risk_level"])

    op.create_table(
        "auditor_feedback",
        _uuid_pk(),
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "risk_result_id",
            UUID(as_uuid=True),
            sa.ForeignKey("risk_results.id", ondelete="SET NULL"),
        ),
        sa.Column("auditor_username", sa.Text, nullable=False),
        sa.Column("text_th", sa.Text, nullable=False),
        # Filled by the batch sentiment flow; NULL until analyzed
        sa.Column("sentiment", sa.Text),
        sa.Column("concern_tags", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "sentiment IS NULL OR sentiment IN ('POSITIVE', 'NEUTRAL', 'NEGATIVE')",
            name="ck_auditor_feedback_sentiment",
        ),
    )
    op.create_index("ix_auditor_feedback_project", "auditor_feedback", ["project_id"])


def downgrade() -> None:
    op.drop_table("auditor_feedback")
    op.drop_table("risk_results")
    op.drop_table("regulations")
    op.drop_table("chunks")
    op.drop_table("documents")
    op.drop_table("budget_lines")
    op.drop_table("projects")
    op.drop_table("sub_districts")
    op.execute("DROP EXTENSION IF EXISTS vector")
