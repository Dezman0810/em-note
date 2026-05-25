"""partial / composite indexes for hot list and tag queries

Revision ID: 202605211200
Revises: 202605121000
"""

from typing import Sequence, Union

from alembic import op

revision: str = "202605211200"
down_revision: Union[str, None] = "202605121000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Списки «мои активные заметки» с сортировкой по updated_at
    op.execute(
        """
        CREATE INDEX ix_notes_owner_active_updated_at
        ON notes (owner_id, updated_at DESC)
        WHERE deleted_at IS NULL
        """
    )
    # Корзина: owner_id + порядок по deleted_at
    op.execute(
        """
        CREATE INDEX ix_notes_owner_trash_deleted_at
        ON notes (owner_id, deleted_at DESC)
        WHERE deleted_at IS NOT NULL
        """
    )
    # Напоминания: владелец + диапазон reminder_at среди активных
    op.execute(
        """
        CREATE INDEX ix_notes_owner_active_reminder_at
        ON notes (owner_id, reminder_at)
        WHERE deleted_at IS NULL AND reminder_at IS NOT NULL
        """
    )
    # Фильтр по tag_id при выборках из note_tags (PK ведёт с note_id)
    op.execute(
        "CREATE INDEX ix_note_tags_tag_id_note_id ON note_tags (tag_id, note_id)"
    )
    # Персональные теги: выборки по note_id из scope + user_id (PK начинается с user_id)
    op.execute(
        """
        CREATE INDEX ix_note_user_personal_tags_note_user
        ON note_user_personal_tags (note_id, user_id)
        """
    )


def downgrade() -> None:
    op.drop_index("ix_note_user_personal_tags_note_user", table_name="note_user_personal_tags")
    op.drop_index("ix_note_tags_tag_id_note_id", table_name="note_tags")
    op.drop_index("ix_notes_owner_active_reminder_at", table_name="notes")
    op.drop_index("ix_notes_owner_trash_deleted_at", table_name="notes")
    op.drop_index("ix_notes_owner_active_updated_at", table_name="notes")
