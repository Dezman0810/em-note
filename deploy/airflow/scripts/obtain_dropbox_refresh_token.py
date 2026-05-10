#!/usr/bin/env python3
"""
Одноразовый помощник Dropbox OAuth (offline → refresh_token).
Запускай на СВОЕМ компьютере (не обязательно в Docker):

  cd путь-к-em-note
  python deploy/airflow/scripts/obtain_dropbox_refresh_token.py

Заранее в консоли Dropbox в Redirect URIs ДОЛЖЕН быть ровно тот же URI, что ниже ↓
"""
from __future__ import annotations

import json
import os
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

REDIRECT_URI = "http://127.0.0.1:8756/dropbox-callback"
PORT = 8756

# Без параметра scope Dropbox запрашивает все разрешения, уже «подтверждённые» для приложения
# на вкладке Permissions (обязательно нажать Submit внизу страницы).
# Если передать scope вручную и приложению эти пункты не одобрены — будет
# «No scope requested can be granted for this app».
# Опционально: set DROPBOX_OAUTH_SCOPES="files.content.write" перед запуском.


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
    _Captured.code = None
    _Captured.err_msg = None

    print(
        "=" * 72,
        "\n1. Создайте приложение: https://www.dropbox.com/developers/apps",
        "\n2. Permissions: files.content.write (+ read). Внизу вкладки нажмите Submit — иначе OAuth не выдаст scope.",
        f"\n3. В приложении добавьте ТОЧНО этот Redirect URI:",
        f"\n   {REDIRECT_URI}",
        "\n4. Укажите ниже App key и App secret (Settings вкладки).",
        "\n" + "=" * 72,
    )
    app_key = input("\nDROPBOX APP KEY: ").strip()
    app_secret = input("DROPBOX APP SECRET: ").strip()
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
    print("✓ Получено. Добавьте в файл deploy/airflow/airflow.env (ключи держите в секрете):")
    print("=" * 72)
    lines = "\n".join(
        [
            f"DROPBOX_APP_KEY={app_key}",
            f"DROPBOX_APP_SECRET={app_secret}",
            f"DROPBOX_REFRESH_TOKEN={refresh}",
            "# Очистите DROPBOX_ACCESS_TOKEN= (пустая строка), иначе DAG возьмёт его вместо refresh.",
            "DROPBOX_REMOTE_ROOT=/",
            "# «Full Dropbox» → свой путь, напр. /em-note-backups",
        ]
    )
    print("\n", lines.replace("\n", "\n "), "\n", sep="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
