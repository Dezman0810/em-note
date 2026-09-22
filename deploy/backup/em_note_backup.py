#!/usr/bin/env python3
"""Ежедневный бэкап em-note в Dropbox — замена DAG `em_note_db_backup` из Airflow.

Делает то же самое: `pg_dump` базы и `tar.gz` каталога вложений, затем загрузка
в `{DROPBOX_REMOTE_ROOT}/{ГГГГ-ММ-ДД}/`. В отличие от Airflow не нужен ни
планировщик с веб-интерфейсом (около 500 МБ RAM), ни доступ к docker.sock: том
вложений примонтирован напрямую, а расписание — обычный цикл ожидания.

Команды:
  daemon                  ждать BACKUP_TIME каждый день и делать бэкап (режим контейнера)
  backup                  один прогон прямо сейчас
  list [ГГГГ-ММ-ДД]       что лежит в Dropbox
  restore ГГГГ-ММ-ДД      восстановить базу и вложения из копии за этот день

Переменные окружения описаны в deploy/backup/README.md.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

#: Одним запросом Dropbox принимает до 150 МБ; крупнее — сессией по частям.
SINGLE_SHOT_LIMIT = 140 * 1024 * 1024
CHUNK_SIZE = 8 * 1024 * 1024
HTTP_TIMEOUT = 300


def env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def tz() -> ZoneInfo:
    try:
        return ZoneInfo(env("BACKUP_TZ", "Europe/Moscow"))
    except Exception:
        return ZoneInfo("UTC")


def log(message: str) -> None:
    stamp = datetime.now(tz()).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] {message}", flush=True)


class DropboxError(RuntimeError):
    pass


def _http(
    url: str,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> bytes:
    req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        raise DropboxError(f"{url} -> HTTP {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise DropboxError(f"{url} -> сеть недоступна: {e.reason}") from e


def access_token() -> str:
    """Короткоживущий токен по refresh-токену; или готовый DROPBOX_ACCESS_TOKEN."""
    refresh = env("DROPBOX_REFRESH_TOKEN")
    app_key = env("DROPBOX_APP_KEY")
    app_secret = env("DROPBOX_APP_SECRET")
    if refresh and app_key and app_secret:
        payload = urllib.parse.urlencode(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh,
                "client_id": app_key,
                "client_secret": app_secret,
            }
        ).encode()
        raw = _http(
            "https://api.dropbox.com/oauth2/token",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        token = json.loads(raw).get("access_token", "")
        if not token:
            raise DropboxError("Dropbox не вернул access_token по refresh-токену")
        return token

    direct = env("DROPBOX_ACCESS_TOKEN")
    if direct:
        return direct
    raise DropboxError(
        "Нет доступа к Dropbox: задайте DROPBOX_REFRESH_TOKEN + DROPBOX_APP_KEY + "
        "DROPBOX_APP_SECRET (рекомендуется) или DROPBOX_ACCESS_TOKEN."
    )


def remote_root() -> str:
    """У приложения с доступом только к своей папке корень API — уже она, без /Apps/..."""
    root = env("DROPBOX_REMOTE_ROOT", "/")
    if not root.startswith("/"):
        root = "/" + root
    return "" if root == "/" else root.rstrip("/")


def rpc(token: str, endpoint: str, payload: dict) -> dict:
    raw = _http(
        f"https://api.dropboxapi.com/2/{endpoint}",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    return json.loads(raw) if raw else {}


def upload(token: str, local: Path, remote: str) -> None:
    size = local.stat().st_size
    common = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/octet-stream",
    }

    if size <= SINGLE_SHOT_LIMIT:
        arg = {"path": remote, "mode": "overwrite", "mute": True}
        _http(
            "https://content.dropboxapi.com/2/files/upload",
            data=local.read_bytes(),
            headers={**common, "Dropbox-API-Arg": json.dumps(arg)},
        )
        return

    # Крупные архивы вложений — сессией по частям: у DAG такие копии падали по лимиту.
    with local.open("rb") as f:
        first = f.read(CHUNK_SIZE)
        started = json.loads(
            _http(
                "https://content.dropboxapi.com/2/files/upload_session/start",
                data=first,
                headers={**common, "Dropbox-API-Arg": json.dumps({"close": False})},
            )
        )
        session_id = started["session_id"]
        offset = len(first)

        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            arg = {"cursor": {"session_id": session_id, "offset": offset}}
            _http(
                "https://content.dropboxapi.com/2/files/upload_session/append_v2",
                data=chunk,
                headers={**common, "Dropbox-API-Arg": json.dumps(arg)},
            )
            offset += len(chunk)

        finish = {
            "cursor": {"session_id": session_id, "offset": offset},
            "commit": {"path": remote, "mode": "overwrite", "mute": True},
        }
        _http(
            "https://content.dropboxapi.com/2/files/upload_session/finish",
            data=b"",
            headers={**common, "Dropbox-API-Arg": json.dumps(finish)},
        )


def download(token: str, remote: str, local: Path) -> None:
    raw = _http(
        "https://content.dropboxapi.com/2/files/download",
        data=b"",
        headers={
            "Authorization": f"Bearer {token}",
            "Dropbox-API-Arg": json.dumps({"path": remote}),
        },
    )
    local.write_bytes(raw)


def list_folder(token: str, path: str) -> list[dict]:
    out: list[dict] = []
    page = rpc(token, "files/list_folder", {"path": path, "limit": 2000})
    out.extend(page.get("entries", []))
    while page.get("has_more"):
        page = rpc(token, "files/list_folder/continue", {"cursor": page["cursor"]})
        out.extend(page.get("entries", []))
    return out


def pg_env() -> dict[str, str]:
    e = os.environ.copy()
    password = env("PGPASSWORD")
    if password:
        e["PGPASSWORD"] = password
    return e


def attachments_dir() -> Path:
    return Path(env("ATTACHMENTS_DIR", "/mnt/attachments"))


def run_backup() -> list[str]:
    now = datetime.now(tz())
    stamp = now.strftime("%Y%m%d_%H%M%S")
    day = now.strftime("%Y-%m-%d")
    dbname = env("PGDATABASE", "note")

    with tempfile.TemporaryDirectory(prefix="em_note_backup_") as tmp:
        tmpdir = Path(tmp)
        sql_path = tmpdir / f"note_{stamp}.sql"
        tar_path = tmpdir / f"attachments_{stamp}.tar.gz"

        log(f"pg_dump базы {dbname}")
        with sql_path.open("wb") as f:
            subprocess.run(
                [
                    "pg_dump",
                    "-h",
                    env("PGHOST", "db"),
                    "-p",
                    env("PGPORT", "5432"),
                    "-U",
                    env("PGUSER", "postgres"),
                    "--clean",
                    "--if-exists",
                    dbname,
                ],
                stdout=f,
                check=True,
                env=pg_env(),
            )
        if sql_path.stat().st_size < 1000:
            raise RuntimeError(f"Дамп базы подозрительно мал: {sql_path.stat().st_size} Б")

        src = attachments_dir()
        log(f"архив вложений из {src}")
        with tar_path.open("wb") as f:
            subprocess.run(["tar", "czf", "-", "-C", str(src), "."], stdout=f, check=True)
        if tar_path.stat().st_size < 22:
            raise RuntimeError("Архив вложений пуст")

        token = access_token()
        remote_dir = f"{remote_root()}/{day}"
        uploaded: list[str] = []
        for path in (sql_path, tar_path):
            remote = f"{remote_dir}/{path.name}"
            megabytes = path.stat().st_size / 1024 / 1024
            log(f"загрузка {path.name} ({megabytes:.1f} МБ) -> {remote}")
            upload(token, path, remote)
            uploaded.append(remote)

    cleanup_old(token)
    log("готово: " + ", ".join(uploaded))
    return uploaded


def cleanup_old(token: str) -> None:
    """Старые папки с копиями. По умолчанию (0) не удаляем ничего."""
    try:
        keep_days = int(env("BACKUP_KEEP_DAYS", "0"))
    except ValueError:
        keep_days = 0
    if keep_days <= 0:
        return

    edge = (datetime.now(tz()) - timedelta(days=keep_days)).strftime("%Y-%m-%d")
    for entry in list_folder(token, remote_root()):
        name = entry.get("name", "")
        if entry.get(".tag") != "folder" or len(name) != 10:
            continue
        if name < edge:
            log(f"удаляю копию старше {keep_days} дн.: {name}")
            rpc(token, "files/delete_v2", {"path": f"{remote_root()}/{name}"})


def restore(day: str, sql_name: str = "", tar_name: str = "") -> None:
    token = access_token()
    remote_dir = f"{remote_root()}/{day}"
    entries = [e for e in list_folder(token, remote_dir) if e.get(".tag") == "file"]
    if not entries:
        raise RuntimeError(f"В {remote_dir} нет файлов")

    def pick(prefix: str, explicit: str) -> str:
        if explicit:
            return explicit
        names = sorted(e["name"] for e in entries if e["name"].startswith(prefix))
        if not names:
            raise RuntimeError(f"В {remote_dir} нет файла {prefix}*")
        return names[-1]

    sql_file = pick("note_", sql_name)
    tar_file = pick("attachments_", tar_name)

    with tempfile.TemporaryDirectory(prefix="em_note_restore_") as tmp:
        tmpdir = Path(tmp)
        sql_path = tmpdir / sql_file
        tar_path = tmpdir / tar_file
        log(f"скачиваю {sql_file} и {tar_file}")
        download(token, f"{remote_dir}/{sql_file}", sql_path)
        download(token, f"{remote_dir}/{tar_file}", tar_path)

        log("восстанавливаю базу")
        with sql_path.open("rb") as f:
            subprocess.run(
                [
                    "psql",
                    "-h",
                    env("PGHOST", "db"),
                    "-p",
                    env("PGPORT", "5432"),
                    "-U",
                    env("PGUSER", "postgres"),
                    "-d",
                    env("PGDATABASE", "note"),
                    "-v",
                    "ON_ERROR_STOP=0",
                ],
                stdin=f,
                check=True,
                env=pg_env(),
            )

        dst = attachments_dir()
        log(f"распаковываю вложения в {dst} (каталог очищается)")
        for item in dst.iterdir():
            subprocess.run(["rm", "-rf", str(item)], check=True)
        subprocess.run(["tar", "xzf", str(tar_path), "-C", str(dst)], check=True)

    log("восстановление завершено; перезапустите api, чтобы сбросить кеш соединений")


def next_run(now: datetime) -> datetime:
    raw = env("BACKUP_TIME", "03:30")
    try:
        hour, minute = (int(x) for x in raw.split(":", 1))
    except ValueError:
        hour, minute = 3, 30
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return target if target > now else target + timedelta(days=1)


def safe_backup() -> None:
    """Сбой не должен ронять контейнер: пробуем ещё раз через 15 минут."""
    for attempt in (1, 2):
        try:
            run_backup()
            return
        except Exception as e:
            log(f"ОШИБКА бэкапа (попытка {attempt}): {e}")
            if attempt == 1:
                time.sleep(15 * 60)
    log("бэкап не удался — ждём следующего дня")


def daemon() -> None:
    log(f"запуск: бэкап каждый день в {env('BACKUP_TIME', '03:30')} ({tz().key})")
    if env("BACKUP_ON_START", "0") in {"1", "true", "yes"}:
        safe_backup()
    while True:
        now = datetime.now(tz())
        target = next_run(now)
        seconds = (target - now).total_seconds()
        log(f"следующий бэкап: {target:%Y-%m-%d %H:%M} (через {seconds / 3600:.1f} ч)")
        time.sleep(seconds)
        safe_backup()


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else "daemon"
    if command == "daemon":
        daemon()
    elif command == "backup":
        run_backup()
    elif command == "list":
        token = access_token()
        path = f"{remote_root()}/{argv[2]}" if len(argv) > 2 else remote_root()
        for entry in sorted(list_folder(token, path), key=lambda e: e.get("name", "")):
            size = entry.get("size")
            suffix = f"  {size / 1024 / 1024:.1f} МБ" if size else ""
            print(f"{entry.get('.tag', '?'):6} {entry.get('name', '')}{suffix}")
    elif command == "restore":
        if len(argv) < 3:
            print("Укажите дату: restore ГГГГ-ММ-ДД [note_*.sql] [attachments_*.tar.gz]")
            return 2
        restore(argv[2], argv[3] if len(argv) > 3 else "", argv[4] if len(argv) > 4 else "")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
