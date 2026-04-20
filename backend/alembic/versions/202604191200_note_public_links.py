"""note_public_links

Revision ID: 003_public_links
Revises: 002_folders
Create Date: 2026-04-19

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003_public_links"
down_revision: Union[str, None] = "002_folders"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "note_public_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("note_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token", sa.String(length=96), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["note_id"], ["notes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("note_id"),
    )
    op.create_index(op.f("ix_note_public_links_note_id"), "note_public_links", ["note_id"], unique=True)
    op.create_index(op.f("ix_note_public_links_token"), "note_public_links", ["token"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_note_public_links_token"), table_name="note_public_links")
    op.drop_index(op.f("ix_note_public_links_note_id"), table_name="note_public_links")
    op.drop_table("note_public_links")
