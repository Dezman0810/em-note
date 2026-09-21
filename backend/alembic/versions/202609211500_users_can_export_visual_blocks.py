"""users: can_export_schemas, can_export_mindmaps, can_export_diagrams

Revision ID: 202609211500
Revises: 202609122300
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609211500"
down_revision: Union[str, None] = "202609122300"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_bool_column(name: str) -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if any(c["name"] == name for c in insp.get_columns("users")):
        return
    op.add_column(
        "users",
        sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def _drop_bool_column(name: str) -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if not any(c["name"] == name for c in insp.get_columns("users")):
        return
    op.drop_column("users", name)


def upgrade() -> None:
    _add_bool_column("can_export_schemas")
    _add_bool_column("can_export_mindmaps")
    _add_bool_column("can_export_diagrams")


def downgrade() -> None:
    _drop_bool_column("can_export_diagrams")
    _drop_bool_column("can_export_mindmaps")
    _drop_bool_column("can_export_schemas")
