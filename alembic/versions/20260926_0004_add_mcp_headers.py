"""add mcp server headers

Revision ID: 20260926_0004
Revises: 20260926_0003
Create Date: 2026-09-26
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260926_0004"
down_revision: str | None = "20260926_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "mcp_server",
        sa.Column("headers", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json"))
    )
    op.alter_column("mcp_server", "headers", server_default=None)


def downgrade() -> None:
    op.drop_column("mcp_server", "headers")
