"""initial schema

Revision ID: 8830587ef153
Revises:
Create Date: 2026-03-14 03:00:10.596437

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "8830587ef153"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Reusable JSON column type: JSONB on PostgreSQL, plain JSON on SQLite
_jsonb = postgresql.JSONB(astext_type=Text()).with_variant(
    sa.JSON(), "sqlite"
)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "agents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column(
            "model_role",
            sa.Enum("builder", "worker", name="modelrole"),
            nullable=False,
        ),
        sa.Column("model_override", sa.String(length=255), nullable=True),
        sa.Column("tools", _jsonb, nullable=False),
        sa.Column("subagents", _jsonb, nullable=False),
        sa.Column("triggers", _jsonb, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "builder_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "proposed",
                "confirmed",
                "cancelled",
                name="sessionstatus",
            ),
            nullable=False,
        ),
        sa.Column("messages", _jsonb, nullable=False),
        sa.Column("proposed_config", _jsonb, nullable=True),
        sa.Column(
            "confirmed_agent_id", sa.String(length=36), nullable=True
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "runs",
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "running",
                "completed",
                "failed",
                "cancelled",
                name="runstatus",
            ),
            nullable=False,
        ),
        sa.Column("input_message", sa.Text(), nullable=False),
        sa.Column("output", sa.Text(), nullable=False),
        sa.Column("structured_output", _jsonb, nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("token_usage", _jsonb, nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index(
        op.f("ix_runs_agent_id"), "runs", ["agent_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_runs_agent_id"), table_name="runs")
    op.drop_table("runs")
    op.drop_table("builder_sessions")
    op.drop_table("agents")
