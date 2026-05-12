"""log outbound note emails per note

Revision ID: 202605121000
Revises: 202605111200
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202605121000"
down_revision: Union[str, None] = "202605111200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "note_mail_sends",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("note_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sender_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("to_addresses", sa.Text(), nullable=False),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["note_id"], ["notes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_note_mail_sends_note_id"), "note_mail_sends", ["note_id"])
    op.create_index(op.f("ix_note_mail_sends_sent_at"), "note_mail_sends", ["sent_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_note_mail_sends_sent_at"), table_name="note_mail_sends")
    op.drop_index(op.f("ix_note_mail_sends_note_id"), table_name="note_mail_sends")
    op.drop_table("note_mail_sends")
