"""habits: personal weekday habits and daily checks

Revision ID: 202609061800
Revises: 202607091200
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609061800"
down_revision: Union[str, None] = "202607091200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "habits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("icon", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("weekdays", sa.ARRAY(sa.SmallInteger()), nullable=False),
        sa.Column("target_days", sa.SmallInteger(), nullable=False, server_default="5"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_habits_user_id", "habits", ["user_id"])
    op.create_table(
        "habit_checks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("habit_id", sa.Uuid(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["habit_id"], ["habits.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("habit_id", "day", name="uq_habit_checks_habit_day"),
    )
    op.create_index("ix_habit_checks_habit_id", "habit_checks", ["habit_id"])


def downgrade() -> None:
    op.drop_index("ix_habit_checks_habit_id", table_name="habit_checks")
    op.drop_table("habit_checks")
    op.drop_index("ix_habits_user_id", table_name="habits")
    op.drop_table("habits")
