"""preset: tag_match_all (AND across + tags)

Revision ID: 202605251200
Revises: 202605211400
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202605251200"
down_revision: Union[str, None] = "202605211400"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_note_filter_presets",
        sa.Column(
            "tag_match_all",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.alter_column(
        "user_note_filter_presets",
        "tag_match_all",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("user_note_filter_presets", "tag_match_all")
