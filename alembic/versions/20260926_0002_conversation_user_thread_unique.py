"""scope conversation thread uniqueness to user

Revision ID: 20260926_0002
Revises: 20260926_0001
Create Date: 2026-09-26
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260926_0002"
down_revision: str | None = "20260926_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_conversation_thread_id", table_name="conversation")
    op.create_index("ix_conversation_thread_id", "conversation", ["thread_id"], unique=False)
    op.create_unique_constraint(
        "uq_conversation_user_thread",
        "conversation",
        ["user_id", "thread_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_conversation_user_thread", "conversation", type_="unique")
    op.drop_index("ix_conversation_thread_id", table_name="conversation")
    op.create_index("ix_conversation_thread_id", "conversation", ["thread_id"], unique=True)
