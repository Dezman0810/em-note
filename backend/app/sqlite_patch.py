"""Добавляет таблицу folders и колонку notes.folder_id в уже существующую SQLite БД."""

from sqlalchemy import inspect, text


def apply_sqlite_folder_schema(sync_conn) -> None:
    from app.models.folder import Folder

    insp = inspect(sync_conn)
    if not insp.has_table("folders"):
        Folder.__table__.create(sync_conn, checkfirst=True)
    note_cols = {c["name"] for c in insp.get_columns("notes")}
    if "folder_id" not in note_cols:
        sync_conn.execute(text("ALTER TABLE notes ADD COLUMN folder_id TEXT"))


def ensure_note_accent_column(sync_conn) -> None:
    """Колонка цветовой метки заметки (hex #rrggbb или пусто). SQLite и PostgreSQL."""
    insp = inspect(sync_conn)
    if not insp.has_table("notes"):
        return
    note_cols = {c["name"] for c in insp.get_columns("notes")}
    if "accent_color" in note_cols:
        return
    sync_conn.execute(
        text("ALTER TABLE notes ADD COLUMN accent_color VARCHAR(16) NOT NULL DEFAULT ''")
    )
