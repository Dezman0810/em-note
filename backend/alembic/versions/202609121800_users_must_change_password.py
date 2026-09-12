"""users.must_change_password after admin reset

Revision ID: 202609121800
Revises: 202609062200
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609121800"
down_revision: Union[str, None] = "202609062200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if any(c["name"] == "must_change_password" for c in insp.get_columns("users")):
        return
    op.add_column(
        "users",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if not any(c["name"] == "must_change_password" for c in insp.get_columns("users")):
        return
    op.drop_column("users", "must_change_password")
