"""
Ежедневный бэкап em-note только в Dropbox (календарные дни UTC).

Во временной папке контейнера: pg_dump + tar вложений → upload → удаление.

``deploy/airflow/airflow.env``:
  - ``DROPBOX_ACCESS_TOKEN`` (Generated access token), или
  - ``DROPBOX_REFRESH_TOKEN`` + ``DROPBOX_APP_KEY`` + ``DROPBOX_APP_SECRET``

Путь: ``{DROPBOX_REMOTE_ROOT}/{ds UTC}/{файлы}`` (каждый сегмент с ведущим ``/``).

**App folder:** в API корень уже ваша папка ``Apps/Backap_em_note`` — указывайте ``DROPBOX_REMOTE_ROOT=/``
или подпапку внутри неё (напр. ``/daily``). **Не** указывайте ``/Apps/...`` — это каталог аккаунта,
запросы с таким префиксом для приложения только с «App folder» обычно отклоняются.

**Full Dropbox:** свой каталог, напр. ``/em-note-backups``.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from airflow import DAG
from airflow.hooks.base import BaseHook
from airflow.operators.python import PythonOperator

from em_note_dropbox_util import (
    attachments_mount_path,
    attachments_use_host_mount,
    attachments_volume,
    dropbox_client,
    dropbox_missing_message,
    normalized_remote_root,
)


_MSK_TZ = ZoneInfo("Europe/Moscow")
_DROPBOX_UPLOAD_LIMIT_BYTES = int(145 * 1024 * 1024)


def _upload_to_dropbox(
    *, execution_date_ds: str, note_path: Path, att_path: Path
) -> list[str]:
    from dropbox.files import WriteMode

    remote_root = normalized_remote_root()
    dbx = dropbox_client()

    remote_dir = f"{remote_root}/{execution_date_ds}".replace("//", "/")
    if not remote_dir.startswith("/"):
        remote_dir = "/" + remote_dir

    uploaded: list[str] = []
    for path in (note_path, att_path):
        data = path.read_bytes()
        if len(data) > _DROPBOX_UPLOAD_LIMIT_BYTES:
            raise RuntimeError(
                f"{path.name} слишком большой для files_upload ({len(data)} B)"
            )
        remote_file = f"{remote_dir}/{path.name}".replace("//", "/")
        dbx.files_upload(data, remote_file, mode=WriteMode.overwrite)
        uploaded.append(remote_file)

    return uploaded


def backup_em_note_to_dropbox(execution_date_ds: str) -> dict[str, str | list[str]]:
    hint = dropbox_missing_message()
    if hint:
        raise RuntimeError(hint)

    stamp = datetime.now(_MSK_TZ).strftime("%Y%m%d_%H%M%S")
    note_name = f"note_{stamp}.sql"
    att_name = f"attachments_{stamp}.tar.gz"

    conn = BaseHook.get_connection("postgres_em_note")
    dbname = (conn.schema or "note").strip() or "note"
    env = os.environ.copy()
    if conn.password:
        env["PGPASSWORD"] = conn.password

    pg_cmd = [
        "pg_dump",
        "-h",
        conn.host,
        "-p",
        str(conn.port or 5432),
        "-U",
        conn.login,
        "--clean",
        "--if-exists",
        dbname,
    ]
    vol = attachments_volume()
    docker_cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{vol}:/from:ro",
        "alpine",
        "tar",
        "czf",
        "-",
        "-C",
        "/from",
        ".",
    ]

    remote_root = normalized_remote_root()

    with tempfile.TemporaryDirectory(prefix="em_note_backup_") as tmp:
        tmpdir = Path(tmp)
        note_path = tmpdir / note_name
        att_path = tmpdir / att_name

        with note_path.open("wb") as f:
            subprocess.run(pg_cmd, stdout=f, check=True, env=env, stderr=subprocess.DEVNULL)

        if note_path.stat().st_size < 1000:
            raise RuntimeError(f"Дамп БД подозрительно мал: {note_name}")

        with att_path.open("wb") as f:
            if attachments_use_host_mount():
                subprocess.run(
                    ["tar", "czf", "-", "-C", str(attachments_mount_path()), "."],
                    stdout=f,
                    check=True,
                    stderr=subprocess.DEVNULL,
                )
            else:
                subprocess.run(
                    docker_cmd,
                    stdout=f,
                    check=True,
                    stderr=subprocess.DEVNULL,
                )

        att_size = att_path.stat().st_size
        if att_size < 22:
            raise RuntimeError(
                f"Архив вложений почти пуст: {att_name} ({att_size} B)"
            )

        try:
            dropbox_paths = _upload_to_dropbox(
                execution_date_ds=execution_date_ds,
                note_path=note_path,
                att_path=att_path,
            )
        except Exception as e:
            msg = str(e).lower()
            if ("invalid" in msg and "path" in msg) or "not_authorized" in msg:
                raise RuntimeError(
                    "Dropbox отклонил путь. У приложений с доступом только к «App folder» "
                    "корнем в API считается уже ваша папка приложения: задайте "
                    "DROPBOX_REMOTE_ROOT=/ или /подпапка; не используйте /Apps/.... "
                    f"Исходная ошибка: {e}"
                ) from e
            raise

    return {
        "day_utc": execution_date_ds,
        "stamp_moscow": stamp,
        "dropbox_paths": dropbox_paths,
        "remote_dir": f"{remote_root}/{execution_date_ds}".replace("//", "/"),
    }


default_args = {
    "owner": "em-note",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=3),
}

with DAG(
    dag_id="em_note_db_backup",
    default_args=default_args,
    description="Ежедневный бэкап БД и вложений только в Dropbox (без сохранения на диск хоста)",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["em-note", "backup", "postgres", "attachments", "dropbox"],
) as dag:
    backup = PythonOperator(
        task_id="backup_to_dropbox",
        python_callable=backup_em_note_to_dropbox,
        op_kwargs={"execution_date_ds": "{{ ds }}"},
    )
