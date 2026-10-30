"""Distinguish free chat questions from explicitly filed complaints."""

from alembic import op
import sqlalchemy as sa

revision = "4ab2e6d1c901"
down_revision = "db75e1fbabc1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tickets",
        sa.Column("intake", sa.String(20), nullable=False, server_default="complaint"),
    )


def downgrade():
    op.drop_column("tickets", "intake")
