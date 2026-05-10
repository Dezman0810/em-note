"""Общие функции Dropbox и путей для DAG em-note (без определений DAG)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from airflow.models import Variable

# Том вложений смонтирован в контейнер scheduler (docker-compose.airflow.vps.yml).
_DEFAULT_ATTACHMENTS_MOUNT = "/mnt/em_note_attachments"


def attachments_volume() -> str:
    key = "EM_NOTE_ATTACHMENTS_VOLUME"
    val = (Variable.get(key, default_var="") or "").strip()
    if val:
        return val
    return os.environ.get(key, "em-note_em_note_attachments").strip()


def attachments_mount_path() -> Path:
    raw = (os.environ.get("EM_NOTE_ATTACHMENTS_MOUNT_PATH") or "").strip()
    return Path(raw or _DEFAULT_ATTACHMENTS_MOUNT)


def attachments_use_host_mount() -> bool:
    """True, если каталог тома доступен в ФС контейнера (VPS) — без ``docker run`` / alpine."""
    p = attachments_mount_path()
    try:
        return p.is_dir()
    except OSError:
        return False


def clear_attachments_mount(mount: Path) -> None:
    """Очистка содержимого тома (аналог ``find … -mindepth 1 -delete``)."""
    for child in mount.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def dropbox_missing_message() -> str | None:
    access = (os.environ.get("DROPBOX_ACCESS_TOKEN") or "").strip()
    refresh = (os.environ.get("DROPBOX_REFRESH_TOKEN") or "").strip()
    app_key = (os.environ.get("DROPBOX_APP_KEY") or "").strip()
    app_secret = (os.environ.get("DROPBOX_APP_SECRET") or "").strip()
    if refresh and app_key and app_secret:
        return None
    if access:
        return None
    parts = ["DROPBOX_REFRESH_TOKEN или DROPBOX_ACCESS_TOKEN"]
    if not refresh:
        if not app_key:
            parts.append("DROPBOX_APP_KEY")
        if not app_secret:
            parts.append("DROPBOX_APP_SECRET")
    return (
        "Нет учётных данных Dropbox. Задайте в deploy/airflow/airflow.env "
        + ", ".join(parts)
        + " и пересоздайте контейнеры: docker compose -f docker-compose.airflow.yml up -d --force-recreate"
    )


def dropbox_client():
    import dropbox

    app_key = (os.environ.get("DROPBOX_APP_KEY") or "").strip()
    app_secret = (os.environ.get("DROPBOX_APP_SECRET") or "").strip()
    refresh = (os.environ.get("DROPBOX_REFRESH_TOKEN") or "").strip()
    if refresh and app_key and app_secret:
        return dropbox.Dropbox(
            oauth2_refresh_token=refresh,
            app_key=app_key,
            app_secret=app_secret,
        )

    access = (os.environ.get("DROPBOX_ACCESS_TOKEN") or "").strip()
    if access:
        return dropbox.Dropbox(oauth2_access_token=access)

    missing = ["DROPBOX_REFRESH_TOKEN или DROPBOX_ACCESS_TOKEN"]
    if not app_key:
        missing.append("DROPBOX_APP_KEY")
    if not app_secret:
        missing.append("DROPBOX_APP_SECRET")
    raise RuntimeError(
        "Dropbox: задайте в airflow.env "
        + ", ".join(missing)
        + ". Либо только DROPBOX_ACCESS_TOKEN."
    )


def normalized_remote_root() -> str:
    raw = (os.environ.get("DROPBOX_REMOTE_ROOT") or "/").strip()
    if not raw.startswith("/"):
        raw = "/" + raw
    trimmed = raw.rstrip("/")
    return trimmed if trimmed else "/"


def dropbox_path_for_file(*, backup_day: str, filename: str) -> str:
    root = normalized_remote_root()
    p = f"{root}/{backup_day}/{filename}".replace("//", "/")
    if not p.startswith("/"):
        p = "/" + p
    return p
