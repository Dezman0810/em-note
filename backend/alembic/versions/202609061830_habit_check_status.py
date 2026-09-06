"""habit_checks.status: done or missed

Revision ID: 202609061830
Revises: 202609061800
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609061830"
down_revision: Union[str, None] = "202609061800"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "habit_checks",
        sa.Column("status", sa.String(length=12), nullable=False, server_default="done"),
    )


def downgrade() -> None:
    op.drop_column("habit_checks", "status")
