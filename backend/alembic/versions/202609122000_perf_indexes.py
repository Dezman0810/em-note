"""perf: functional/composite indexes for tag lookup, habits order, shares and search

Revision ID: 202609122000
Revises: 202609121800
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609122000"
down_revision: Union[str, None] = "202609121800"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (имя индекса, таблица, DDL) — порядок сохраняется и в downgrade (в обратном виде).
_INDEXES: list[tuple[str, str, str]] = [
    # get_or_create_root_tag: поиск корневой метки по lower(name)
    (
        "ix_tags_user_lower_name_root",
        "tags",
        """
        CREATE INDEX ix_tags_user_lower_name_root
        ON tags (user_id, lower(name))
        WHERE parent_id IS NULL
        """,
    ),
    # habits_for_owner: ORDER BY sort_order, created_at внутри пользователя
    (
        "ix_habits_user_sort_created",
        "habits",
        """
        CREATE INDEX ix_habits_user_sort_created
        ON habits (user_id, sort_order, created_at)
        """,
    ),
    # Проверка дубликата шера и выборка прав в get_note_access
    (
        "ix_note_shares_note_user",
        "note_shares",
        """
        CREATE INDEX ix_note_shares_note_user
        ON note_shares (note_id, shared_with_user_id)
        WHERE shared_with_user_id IS NOT NULL
        """,
    ),
    # claim_invite_shares_for_user: WHERE invite_email IS NOT NULL AND lower(invite_email) = ...
    (
        "ix_note_shares_lower_invite_email",
        "note_shares",
        """
        CREATE INDEX ix_note_shares_lower_invite_email
        ON note_shares (lower(invite_email))
        WHERE invite_email IS NOT NULL
        """,
    ),
]

# Поиск по части слова в заголовке (ILIKE '%...%') индексируется только триграммами.
# Без расширения запрос остаётся корректным, просто планировщик выберет seq scan,
# поэтому недоступный pg_trgm не должен ломать миграцию.
_TRGM_INDEX = "ix_notes_title_trgm"


def _existing_index_names(insp: sa.Inspector, table: str) -> set[str]:
    return {ix["name"] for ix in insp.get_indexes(table) if ix.get("name")}


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    for name, table, ddl in _INDEXES:
        if name in _existing_index_names(insp, table):
            continue
        op.execute(ddl)

    if _TRGM_INDEX not in _existing_index_names(insp, "notes"):
        try:
            with conn.begin_nested():
                conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
                conn.execute(
                    sa.text(
                        f"CREATE INDEX {_TRGM_INDEX} ON notes USING GIN (title gin_trgm_ops)"
                    )
                )
        except sa.exc.SQLAlchemyError:
            # Нет прав на CREATE EXTENSION (managed Postgres) — живём без индекса.
            pass


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if _TRGM_INDEX in _existing_index_names(insp, "notes"):
        op.execute(f"DROP INDEX {_TRGM_INDEX}")
    for name, table, _ddl in reversed(_INDEXES):
        if name in _existing_index_names(insp, table):
            op.execute(f"DROP INDEX {name}")
