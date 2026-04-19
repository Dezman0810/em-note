"""add folders and note.folder_id

Revision ID: 002_folders
Revises: 001_initial
Create Date: 2026-04-02

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002_folders"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "folders",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", name="uq_folder_user_name"),
    )
    op.create_index(op.f("ix_folders_user_id"), "folders", ["user_id"], unique=False)
    op.add_column("notes", sa.Column("folder_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index(op.f("ix_notes_folder_id"), "notes", ["folder_id"], unique=False)
    op.create_foreign_key(
        "notes_folder_id_fkey",
        "notes",
        "folders",
        ["folder_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("notes_folder_id_fkey", "notes", type_="foreignkey")
    op.drop_index(op.f("ix_notes_folder_id"), table_name="notes")
    op.drop_column("notes", "folder_id")
    op.drop_table("folders")
