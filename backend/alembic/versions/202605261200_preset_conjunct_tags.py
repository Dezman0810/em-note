"""preset: conjunct_tag_ids (AND block alongside +/)

Revision ID: 202605261200
Revises: 202605251200
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202605261200"
down_revision: Union[str, None] = "202605251200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_note_filter_presets",
        sa.Column(
            "conjunct_tag_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.alter_column("user_note_filter_presets", "conjunct_tag_ids", server_default=None)


def downgrade() -> None:
    op.drop_column("user_note_filter_presets", "conjunct_tag_ids")
