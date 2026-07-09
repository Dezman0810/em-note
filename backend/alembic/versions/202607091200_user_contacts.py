"""user_contacts: personal email contact book per user

Revision ID: 202607091200
Revises: 202605271200
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202607091200"
down_revision: Union[str, None] = "202605271200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_contacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "email", name="uq_user_contacts_user_email"),
    )
    op.create_index("ix_user_contacts_user_id", "user_contacts", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_contacts_user_id", table_name="user_contacts")
    op.drop_table("user_contacts")
