"""
Восстановление em-note из копии в Dropbox (только ручной запуск).

**Параметры**

1. **Форма Trigger DAG:** *backup_date*, *note_sql*, *attachments_tar*.

2. **JSON конфиг триггера:**

   ``{"backup_date": "2026-05-10", "note_sql": "note_20260510_225145.sql", "attachments_tar": "attachments_20260510_225145.tar.gz"}``

3. **Или** переменные ``EM_NOTE_RESTORE_*`` в ``airflow.env`` / Airflow Variables (если в триггере поле пустое).

Перед распаковкой вложений том **всегда очищается**, затем распаковывается архив (полное восстановление снимка).

Нужны те же Dropbox credentials и ``DROPBOX_REMOTE_ROOT``, что и у ``em_note_db_backup``.
Postgres — ``postgres_em_note``, том — ``EM_NOTE_ATTACHMENTS_VOLUME``.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from airflow import DAG
from airflow.hooks.base import BaseHook
from airflow.models import Variable
from airflow.models.param import Param
from airflow.operators.python import PythonOperator

from em_note_dropbox_util import (
    attachments_mount_path,
    attachments_use_host_mount,
    attachments_volume,
    clear_attachments_mount,
    dropbox_client,
    dropbox_missing_message,
    dropbox_path_for_file,
)

_PG17_SET_DROP = re.compile(r"^\s*SET\s+transaction_timeout\b", re.IGNORECASE)


def _sanitize_pg_dump_sql_for_older_servers(sql_text: str) -> str:
    """Убирает SET transaction_timeout (PG17+), если целевой сервер старше и не знает этот GUC."""
    out: list[str] = []
    for line in sql_text.splitlines(keepends=True):
        if _PG17_SET_DROP.match(line):
            continue
        out.append(line)
    return "".join(out)


def _restore_param(key: str) -> str:
    val = (Variable.get(key, default_var="") or "").strip()
    if val:
        return val
    return (os.environ.get(key) or "").strip()


def _trigger_conf(context: dict[str, Any]) -> dict[str, Any]:
    dr = context.get("dag_run")
    if not dr or not dr.conf:
        return {}
    return dict(dr.conf)


def _str_from_conf_or_env(conf: dict[str, Any], conf_key: str, env_key: str) -> str:
    if conf_key in conf:
        v = conf[conf_key]
        if v is None:
            s = ""
        else:
            s = str(v).strip()
        if s:
            return s
    return _restore_param(env_key)


def restore_em_note_from_dropbox(**context: Any) -> dict[str, str]:
    conf = _trigger_conf(context)

    hint = dropbox_missing_message()
    if hint:
        raise RuntimeError(hint)

    day = _str_from_conf_or_env(conf, "backup_date", "EM_NOTE_RESTORE_BACKUP_DATE")
    sql_name = _str_from_conf_or_env(conf, "note_sql", "EM_NOTE_RESTORE_NOTE_SQL")
    tar_name = _str_from_conf_or_env(conf, "attachments_tar", "EM_NOTE_RESTORE_ATTACHMENTS_TAR")
    missing = [
        label
        for label, v in [
            ("backup_date (или EM_NOTE_RESTORE_BACKUP_DATE)", day),
            ("note_sql (или EM_NOTE_RESTORE_NOTE_SQL)", sql_name),
            ("attachments_tar (или EM_NOTE_RESTORE_ATTACHMENTS_TAR)", tar_name),
        ]
        if not v
    ]
    if missing:
        raise RuntimeError(
            "Не хватает параметров: " + ", ".join(missing) + ". "
            "Укажите их в форме Trigger DAG или в airflow.env."
        )

    sql_remote = dropbox_path_for_file(backup_day=day, filename=sql_name)
    tar_remote = dropbox_path_for_file(backup_day=day, filename=tar_name)

    dbx = dropbox_client()
    conn = BaseHook.get_connection("postgres_em_note")
    dbname = (conn.schema or "note").strip() or "note"
    env = os.environ.copy()
    if conn.password:
        env["PGPASSWORD"] = conn.password
    env.setdefault("PGCLIENTENCODING", "UTF8")

    vol = attachments_volume()

    with tempfile.TemporaryDirectory(prefix="em_note_restore_") as tmp:
        tmpdir = Path(tmp)
        sql_path = tmpdir / sql_name
        tar_path = tmpdir / tar_name

        for remote, dest in ((sql_remote, sql_path), (tar_remote, tar_path)):
            _md, res = dbx.files_download(remote)
            data = res.content
            if not data:
                raise RuntimeError(f"Пустой ответ Dropbox для {remote}")
            dest.write_bytes(data)

        if sql_path.stat().st_size < 100:
            raise RuntimeError(f"SQL подозрительно мал: {sql_name}")
        if tar_path.stat().st_size < 22:
            raise RuntimeError(f"Архив вложений подозрительно мал: {tar_name}")

        sql_raw = sql_path.read_bytes()
        try:
            sql_text = sql_raw.decode("utf-8")
        except UnicodeDecodeError:
            sql_text = sql_raw.decode("utf-8", errors="replace")
        sql_fixed = _sanitize_pg_dump_sql_for_older_servers(sql_text)
        if sql_fixed != sql_text:
            sql_path.write_text(sql_fixed, encoding="utf-8")

        psql = subprocess.run(
            [
                "psql",
                "-X",
                "-h",
                conn.host,
                "-p",
                str(conn.port or 5432),
                "-U",
                conn.login,
                "-d",
                dbname,
                "-v",
                "ON_ERROR_STOP=1",
                "-f",
                str(sql_path),
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        if psql.returncode != 0:
            err_tail = (psql.stderr or "").strip() or (psql.stdout or "").strip() or "(нет текста)"
            raise RuntimeError(
                f"psql завершился с кодом {psql.returncode}. "
                f"Проверьте, что Postgres em-note доступен с хоста Airflow ({conn.host}:{conn.port}), "
                f"и что дамп совместим с этой версией БД. Вывод psql:\n{err_tail}"
            )

        if attachments_use_host_mount():
            clear_attachments_mount(attachments_mount_path())
            with tar_path.open("rb") as tar_f:
                subprocess.run(
                    ["tar", "xzf", "-", "-C", str(attachments_mount_path())],
                    stdin=tar_f,
                    check=True,
                )
        else:
            subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-v",
                    f"{vol}:/to",
                    "alpine",
                    "find",
                    "/to",
                    "-mindepth",
                    "1",
                    "-delete",
                ],
                check=True,
            )

            with tar_path.open("rb") as tar_f:
                subprocess.run(
                    [
                        "docker",
                        "run",
                        "--rm",
                        "-i",
                        "-v",
                        f"{vol}:/to",
                        "alpine",
                        "tar",
                        "xzf",
                        "-",
                        "-C",
                        "/to",
                    ],
                    stdin=tar_f,
                    check=True,
                )

    return {
        "backup_day": day,
        "note_sql": sql_name,
        "attachments_tar": tar_name,
        "sql_dropbox_path": sql_remote,
        "tar_dropbox_path": tar_remote,
        "attachments_cleared_first": "true",
    }


default_args = {
    "owner": "em-note",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 0,
}

with DAG(
    dag_id="em_note_restore_from_dropbox",
    default_args=default_args,
    description="Восстановление БД и вложений из Dropbox (три поля при запуске или .env)",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["em-note", "restore", "postgres", "attachments", "dropbox"],
    params={
        "backup_date": Param(
            "",
            type="string",
            description="Папка в Dropbox (UTC), напр. 2026-05-10",
        ),
        "note_sql": Param(
            "",
            type="string",
            description="Имя файла, напр. note_20260510_225145.sql",
        ),
        "attachments_tar": Param(
            "",
            type="string",
            description="Имя архива, напр. attachments_20260510_225145.tar.gz",
        ),
    },
) as dag:
    restore = PythonOperator(
        task_id="restore_from_dropbox",
        python_callable=restore_em_note_from_dropbox,
    )
