"""add mcp oauth tokens

Revision ID: 20260926_0006
Revises: 20260926_0005
Create Date: 2026-09-26
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260926_0006"
down_revision: str | None = "20260926_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "mcp_server",
        sa.Column("oauth_tokens", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json"))
    )
    op.alter_column("mcp_server", "oauth_tokens", server_default=None)


def downgrade() -> None:
    op.drop_column("mcp_server", "oauth_tokens")
