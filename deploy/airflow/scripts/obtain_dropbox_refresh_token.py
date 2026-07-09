#!/usr/bin/env python3
"""
Одноразовый помощник Dropbox OAuth (offline → refresh_token).
Запускай на СВОЕМ компьютере (не обязательно в Docker):

  cd путь-к-em-note
  python deploy/airflow/scripts/obtain_dropbox_refresh_token.py
  python deploy/airflow/scripts/obtain_dropbox_refresh_token.py --apply

Ключи DROPBOX_APP_KEY / DROPBOX_APP_SECRET подхватываются из deploy/airflow/airflow.env,
если там уже заданы (интерактивный ввод не нужен).

Заранее в консоли Dropbox в Redirect URIs ДОЛЖЕН быть ровно тот же URI, что ниже ↓
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

REDIRECT_URI = "http://127.0.0.1:8756/dropbox-callback"
PORT = 8756

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ENV_PATH = REPO_ROOT / "deploy" / "airflow" / "airflow.env"

# Без параметра scope Dropbox запрашивает все разрешения, уже «подтверждённые» для приложения
# на вкладке Permissions (обязательно нажать Submit внизу страницы).
# Опционально: set DROPBOX_OAUTH_SCOPES="files.content.write" перед запуском.


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _apply_to_airflow_env(
    env_path: Path,
    *,
    app_key: str,
    app_secret: str,
    refresh: str,
    remote_root: str = "/",
) -> None:
    text = env_path.read_text(encoding="utf-8", errors="replace") if env_path.is_file() else ""
    updates = {
        "DROPBOX_APP_KEY": app_key,
        "DROPBOX_APP_SECRET": app_secret,
        "DROPBOX_REFRESH_TOKEN": refresh,
        "DROPBOX_ACCESS_TOKEN": "",
        "DROPBOX_REMOTE_ROOT": remote_root,
    }
    lines = text.splitlines()
    seen: set[str] = set()
    new_lines: list[str] = []
    for raw in lines:
        if "=" not in raw or raw.strip().startswith("#"):
            new_lines.append(raw)
            continue
        key = raw.split("=", 1)[0].strip()
        if key in updates:
            new_lines.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            new_lines.append(raw)
    for key, val in updates.items():
        if key not in seen:
            new_lines.append(f"{key}={val}")
    env_path.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")
    print(f"OK: zapisano v {env_path} (DROPBOX_ACCESS_TOKEN ochischen).")


class _Captured:
    code: str | None = None
    err_msg: str | None = None


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args):  # noqa: A003
        return

    def do_GET(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        if path != "/dropbox-callback":
            self.send_response(404)
            self.end_headers()
            return
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if "error" in qs:
            self.send_response(400)
            self.end_headers()
            _Captured.err_msg = str(
                qs.get("error_description", qs.get("error", ["unknown"]))[0]
            )
            self.wfile.write(b"OAuth error. Check terminal.")
            return
        codes = qs.get("code")
        if not codes:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"No code in URL.")
            return
        _Captured.code = codes[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"OK. You can close this tab.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Получить Dropbox refresh token для Airflow DAG")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Записать ключи в deploy/airflow/airflow.env и очистить DROPBOX_ACCESS_TOKEN",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_PATH,
        help="Путь к airflow.env (по умолчанию deploy/airflow/airflow.env)",
    )
    args = parser.parse_args()

    _Captured.code = None
    _Captured.err_msg = None

    env_vals = _parse_env_file(args.env_file)
    app_key = (os.environ.get("DROPBOX_APP_KEY") or env_vals.get("DROPBOX_APP_KEY") or "").strip()
    app_secret = (
        os.environ.get("DROPBOX_APP_SECRET") or env_vals.get("DROPBOX_APP_SECRET") or ""
    ).strip()
    remote_root = (env_vals.get("DROPBOX_REMOTE_ROOT") or "/").strip() or "/"

    print(
        "=" * 72,
        "\n1. Создайте приложение: https://www.dropbox.com/developers/apps",
        "\n2. Permissions: files.content.write (+ read). Внизу вкладки нажмите Submit — иначе OAuth не выдаст scope.",
        f"\n3. В приложении добавьте ТОЧНО этот Redirect URI:",
        f"\n   {REDIRECT_URI}",
        "\n4. App key / App secret — из Settings (или уже в airflow.env).",
        "\n" + "=" * 72,
    )
    if not app_key:
        app_key = input("\nDROPBOX APP KEY: ").strip()
    else:
        print(f"\nDROPBOX APP KEY: {app_key[:6]}… (из airflow.env)")
    if not app_secret:
        app_secret = input("DROPBOX APP SECRET: ").strip()
    else:
        print("DROPBOX APP SECRET: *** (из airflow.env)")
    if not app_key or not app_secret:
        print("Не заданы key/secret.")
        return 1

    auth_params: dict[str, str] = {
        "client_id": app_key,
        "response_type": "code",
        "token_access_type": "offline",
        "redirect_uri": REDIRECT_URI,
    }
    extra_scope = (os.environ.get("DROPBOX_OAUTH_SCOPES") or "").strip()
    if extra_scope:
        auth_params["scope"] = extra_scope
    auth = "https://www.dropbox.com/oauth2/authorize?" + urllib.parse.urlencode(
        auth_params,
        quote_via=urllib.parse.quote,
    )
    srv = HTTPServer(("127.0.0.1", PORT), _Handler)

    def _poll() -> None:
        srv.handle_request()

    t = threading.Thread(target=_poll, daemon=False)
    t.start()
    print("\nОткрывается браузер. Войдите в Dropbox и разрешите доступ.\nЕсли вкладка не открылась, скопируйте URL:")
    print(auth)
    webbrowser.open(auth)

    t.join(timeout=300)
    srv.server_close()

    if _Captured.err_msg:
        print("Ошибка OAuth:", _Captured.err_msg)
        return 2
    if not _Captured.code:
        print("Не получили code за 300 с. Запустите скрипт снова.")
        return 3

    body = urllib.parse.urlencode(
        {
            "code": _Captured.code,
            "grant_type": "authorization_code",
            "client_id": app_key,
            "client_secret": app_secret,
            "redirect_uri": REDIRECT_URI,
        }
    ).encode()

    req = urllib.request.Request(
        "https://api.dropbox.com/oauth2/token",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            parsed = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        err = e.read().decode(errors="replace")
        print("Dropbox вернул ошибку:", err)
        return 4

    refresh = parsed.get("refresh_token")
    if not refresh:
        print("В ответе нет refresh_token:", parsed)
        return 5

    print("\n" + "=" * 72)
    print("OK: poluchen refresh token. Dobavte v deploy/airflow/airflow.env:")
    print("=" * 72)
    lines = "\n".join(
        [
            f"DROPBOX_APP_KEY={app_key}",
            f"DROPBOX_APP_SECRET={app_secret}",
            f"DROPBOX_REFRESH_TOKEN={refresh}",
            "DROPBOX_ACCESS_TOKEN=",
            f"DROPBOX_REMOTE_ROOT={remote_root}",
            "# «Full Dropbox» → свой путь, напр. /em-note-backups",
        ]
    )
    print("\n", lines.replace("\n", "\n "), "\n", sep="")
    if args.apply:
        _apply_to_airflow_env(
            args.env_file,
            app_key=app_key,
            app_secret=app_secret,
            refresh=refresh,
            remote_root=remote_root,
        )
    else:
        print("Подсказка: повторите с --apply, чтобы записать в airflow.env автоматически.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
