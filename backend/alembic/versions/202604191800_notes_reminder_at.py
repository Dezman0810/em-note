"""notes: reminder_at

Revision ID: 202604191800
Revises: 003_public_links
Create Date: 2026-04-19

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202604191800"
down_revision: Union[str, None] = "003_public_links"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "notes",
        sa.Column("reminder_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_notes_reminder_at", "notes", ["reminder_at"])


def downgrade() -> None:
    op.drop_index("ix_notes_reminder_at", table_name="notes")
    op.drop_column("notes", "reminder_at")
