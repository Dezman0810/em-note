"""habit_checks.comment: note for a day's mark

Revision ID: 202609062200
Revises: 202609062100
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609062200"
down_revision: Union[str, None] = "202609062100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "habit_checks",
        sa.Column("comment", sa.String(length=2000), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("habit_checks", "comment")
