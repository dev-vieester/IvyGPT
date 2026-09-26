"""add user mcp servers

Revision ID: 20260926_0003
Revises: 20260926_0002
Create Date: 2026-09-26
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260926_0003"
down_revision: str | None = "20260926_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mcp_server",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("transport", sa.String(), nullable=False),
        sa.Column("command", sa.String(), nullable=True),
        sa.Column("args", sa.JSON(), nullable=False),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", name="uq_mcp_server_user_name")
    )
    op.create_index(op.f("ix_mcp_server_id"), "mcp_server", ["id"], unique=False)
    op.create_index(op.f("ix_mcp_server_name"), "mcp_server", ["name"], unique=False)
    op.create_index(op.f("ix_mcp_server_user_id"), "mcp_server", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_mcp_server_user_id"), table_name="mcp_server")
    op.drop_index(op.f("ix_mcp_server_name"), table_name="mcp_server")
    op.drop_index(op.f("ix_mcp_server_id"), table_name="mcp_server")
    op.drop_table("mcp_server")
