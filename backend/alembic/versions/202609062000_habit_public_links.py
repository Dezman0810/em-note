"""habit_public_links: view-only share URL for a user's habit board

Revision ID: 202609062000
Revises: 202609061900
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609062000"
down_revision: Union[str, None] = "202609061900"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "habit_public_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token", sa.String(length=96), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
        sa.UniqueConstraint("token"),
    )
    op.create_index("ix_habit_public_links_user_id", "habit_public_links", ["user_id"])
    op.create_index("ix_habit_public_links_token", "habit_public_links", ["token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_habit_public_links_token", table_name="habit_public_links")
    op.drop_index("ix_habit_public_links_user_id", table_name="habit_public_links")
    op.drop_table("habit_public_links")
