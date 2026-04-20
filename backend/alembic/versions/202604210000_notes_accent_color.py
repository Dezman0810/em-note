"""notes: accent_color (цветовая метка)

Revision ID: 202604210000
Revises: 202604201000
Create Date: 2026-04-21

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202604210000"
down_revision: Union[str, None] = "202604201000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if not insp.has_table("notes"):
        return
    if any(c["name"] == "accent_color" for c in insp.get_columns("notes")):
        return
    op.add_column(
        "notes",
        sa.Column(
            "accent_color",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("''"),
        ),
    )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if not insp.has_table("notes"):
        return
    if not any(c["name"] == "accent_color" for c in insp.get_columns("notes")):
        return
    op.drop_column("notes", "accent_color")
