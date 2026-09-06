"""habits.starts_on: schedule is fixed on the habit, not the calendar picker

Revision ID: 202609062100
Revises: 202609062000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609062100"
down_revision: Union[str, None] = "202609062000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("habits", sa.Column("starts_on", sa.Date(), nullable=True))
    op.execute(
        sa.text(
            "UPDATE habits SET starts_on = (timezone('Europe/Moscow', created_at))::date "
            "WHERE starts_on IS NULL"
        )
    )
    op.alter_column("habits", "starts_on", nullable=False)


def downgrade() -> None:
    op.drop_column("habits", "starts_on")
