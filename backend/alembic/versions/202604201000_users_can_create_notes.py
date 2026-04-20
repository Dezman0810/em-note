"""users: can_create_notes (доступ к созданию заметок по решению админа)

Revision ID: 202604201000
Revises: 202604191800
Create Date: 2026-04-20

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202604201000"
down_revision: Union[str, None] = "202604191800"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if any(c["name"] == "can_create_notes" for c in insp.get_columns("users")):
        return
    op.add_column(
        "users",
        sa.Column("can_create_notes", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if not any(c["name"] == "can_create_notes" for c in insp.get_columns("users")):
        return
    op.drop_column("users", "can_create_notes")
