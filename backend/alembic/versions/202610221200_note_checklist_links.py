"""note_checklist_links: ссылка, по которой можно только отмечать чек-боксы

Revision ID: 202610221200
Revises: 202609211500
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202610221200"
down_revision: Union[str, None] = "202609211500"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    if sa.inspect(conn).has_table("note_checklist_links"):
        return
    op.create_table(
        "note_checklist_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("note_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token", sa.String(length=96), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["note_id"], ["notes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_note_checklist_links_note_id"), "note_checklist_links", ["note_id"], unique=True
    )
    op.create_index(
        op.f("ix_note_checklist_links_token"), "note_checklist_links", ["token"], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_note_checklist_links_token"), table_name="note_checklist_links")
    op.drop_index(op.f("ix_note_checklist_links_note_id"), table_name="note_checklist_links")
    op.drop_table("note_checklist_links")
