"""users: email в нижнем регистре + галочка создания заметок у админа по email

Revision ID: 202604211200
Revises: 202604210000
Create Date: 2026-04-21

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202604211200"
down_revision: Union[str, None] = "202604210000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

"""Совпадает с дефолтом settings.admin_email; владелец всегда может создавать заметки."""
_ADMIN_EMAIL = "ramis.idrisov@gmail.com"


def upgrade() -> None:
    conn = op.get_bind()
    if not sa.inspect(conn).has_table("users"):
        return
    op.execute(sa.text("UPDATE users SET email = lower(trim(email))"))
    op.execute(
        sa.text("UPDATE users SET can_create_notes = true WHERE email = :email").bindparams(
            email=_ADMIN_EMAIL
        )
    )


def downgrade() -> None:
    pass
