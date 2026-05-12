"""personal folder placement and personal tags for shared notes

Revision ID: 202605111200
Revises: 202604221800
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202605111200"
down_revision: Union[str, None] = "202604221800"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "note_user_placements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("note_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("folder_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["folder_id"], ["folders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["note_id"], ["notes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "note_id", name="uq_note_user_placement"),
    )
    op.create_index(op.f("ix_note_user_placements_user_id"), "note_user_placements", ["user_id"])
    op.create_index(op.f("ix_note_user_placements_note_id"), "note_user_placements", ["note_id"])
    op.create_index(op.f("ix_note_user_placements_folder_id"), "note_user_placements", ["folder_id"])

    op.create_table(
        "note_user_personal_tags",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("note_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tag_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["note_id"], ["notes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "note_id", "tag_id"),
    )


def downgrade() -> None:
    op.drop_table("note_user_personal_tags")
    op.drop_index(op.f("ix_note_user_placements_folder_id"), table_name="note_user_placements")
    op.drop_index(op.f("ix_note_user_placements_note_id"), table_name="note_user_placements")
    op.drop_index(op.f("ix_note_user_placements_user_id"), table_name="note_user_placements")
    op.drop_table("note_user_placements")
