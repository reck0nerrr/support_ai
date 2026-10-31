"""Persist triage attempts and reproducible evaluation reports."""

from alembic import op
import sqlalchemy as sa

revision = "8e4f9012b615"
down_revision = "4ab2e6d1c901"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "triage_runs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("request_key", sa.String(160), nullable=False),
        sa.Column("run_id", sa.String(80), nullable=False),
        sa.Column("ticket_id", sa.Integer(), sa.ForeignKey("tickets.id")),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("language", sa.String(12), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("needs_human", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(18, 10)),
        sa.Column("input", sa.JSON(), nullable=False),
        sa.Column("output", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in (
        "request_key",
        "run_id",
        "ticket_id",
        "source",
        "provider",
        "language",
        "created_at",
    ):
        op.create_index(f"ix_triage_runs_{column}", "triage_runs", [column])
    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_evaluation_runs_created_at", "evaluation_runs", ["created_at"])


def downgrade():
    op.drop_table("evaluation_runs")
    op.drop_table("triage_runs")
