"""initial postgres schema

Revision ID: 20260926_0001
Revises:
Create Date: 2026-09-26
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260926_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("age", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("google_sub", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id")
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_google_sub"), "users", ["google_sub"], unique=True)
    op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)

    op.create_table(
        "conversation",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("thread_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id")
    )
    op.create_index(op.f("ix_conversation_id"), "conversation", ["id"], unique=False)
    op.create_index(op.f("ix_conversation_thread_id"), "conversation", ["thread_id"], unique=True)
    op.create_index(op.f("ix_conversation_user_id"), "conversation", ["user_id"], unique=False)

    op.create_table(
        "chat_message",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("thread_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id")
    )
    op.create_index(op.f("ix_chat_message_id"), "chat_message", ["id"], unique=False)
    op.create_index(op.f("ix_chat_message_thread_id"), "chat_message", ["thread_id"], unique=False)
    op.create_index(op.f("ix_chat_message_user_id"), "chat_message", ["user_id"], unique=False)

    op.create_table(
        "long_term_memory",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("thread_id", sa.String(), nullable=False),
        sa.Column("memory", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id")
    )
    op.create_index(op.f("ix_long_term_memory_id"), "long_term_memory", ["id"], unique=False)
    op.create_index(op.f("ix_long_term_memory_thread_id"), "long_term_memory", ["thread_id"], unique=False)
    op.create_index(op.f("ix_long_term_memory_user_id"), "long_term_memory", ["user_id"], unique=False)

    op.create_table(
        "refresh_token",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id")
    )
    op.create_index(op.f("ix_refresh_token_id"), "refresh_token", ["id"], unique=False)
    op.create_index(op.f("ix_refresh_token_token_hash"), "refresh_token", ["token_hash"], unique=True)
    op.create_index(op.f("ix_refresh_token_user_id"), "refresh_token", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_refresh_token_user_id"), table_name="refresh_token")
    op.drop_index(op.f("ix_refresh_token_token_hash"), table_name="refresh_token")
    op.drop_index(op.f("ix_refresh_token_id"), table_name="refresh_token")
    op.drop_table("refresh_token")

    op.drop_index(op.f("ix_long_term_memory_user_id"), table_name="long_term_memory")
    op.drop_index(op.f("ix_long_term_memory_thread_id"), table_name="long_term_memory")
    op.drop_index(op.f("ix_long_term_memory_id"), table_name="long_term_memory")
    op.drop_table("long_term_memory")

    op.drop_index(op.f("ix_chat_message_user_id"), table_name="chat_message")
    op.drop_index(op.f("ix_chat_message_thread_id"), table_name="chat_message")
    op.drop_index(op.f("ix_chat_message_id"), table_name="chat_message")
    op.drop_table("chat_message")

    op.drop_index(op.f("ix_conversation_user_id"), table_name="conversation")
    op.drop_index(op.f("ix_conversation_thread_id"), table_name="conversation")
    op.drop_index(op.f("ix_conversation_id"), table_name="conversation")
    op.drop_table("conversation")

    op.drop_index(op.f("ix_users_id"), table_name="users")
    op.drop_index(op.f("ix_users_google_sub"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
