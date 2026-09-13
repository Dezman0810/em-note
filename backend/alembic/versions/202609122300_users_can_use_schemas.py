"""users.can_use_schemas: admin grants the schemas section

Revision ID: 202609122300
Revises: 202609122200
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609122300"
down_revision: Union[str, None] = "202609122200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if any(c["name"] == "can_use_schemas" for c in insp.get_columns("users")):
        return
    op.add_column(
        "users",
        sa.Column("can_use_schemas", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if not any(c["name"] == "can_use_schemas" for c in insp.get_columns("users")):
        return
    op.drop_column("users", "can_use_schemas")
