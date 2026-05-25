#!/usr/bin/env python3
"""Разовое слияние DROPBOX_* из локального airflow.env на VPS без печати значений."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

VPS_HOST = "root@85.198.83.132"
VPS_REMOTE = "/opt/em-note/deploy/airflow/airflow.env"
SSH_KEY = Path.home() / ".ssh" / "id_ed25519_timeweb"


def parse_dropbox_keys(text: str) -> dict[str, str]:
    d: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if key.startswith("DROPBOX_"):
            d[key] = val
    return d


def ssh_base() -> list[str]:
    return [
        "ssh",
        "-i",
        str(SSH_KEY),
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "BatchMode=yes",
        VPS_HOST,
    ]


def main() -> int:
    if not SSH_KEY.is_file():
        print("Нет SSH ключа:", SSH_KEY, file=sys.stderr)
        return 2

    repo = Path(__file__).resolve().parents[2]  # em-note
    local_env = repo / "deploy" / "airflow" / "airflow.env"
    text = local_env.read_text(encoding="utf-8")
    ldb = parse_dropbox_keys(text)
    needed = {
        "DROPBOX_APP_KEY",
        "DROPBOX_APP_SECRET",
        "DROPBOX_REFRESH_TOKEN",
        "DROPBOX_ACCESS_TOKEN",
        "DROPBOX_REMOTE_ROOT",
    }
    if not ldb:
        print("Локально нет DROPBOX_* в airflow.env", file=sys.stderr)
        return 2
    if not needed.issubset(ldb.keys()):
        missing = sorted(needed - ldb.keys())
        print("В локальном env не хватает:", ", ".join(missing), file=sys.stderr)
        return 2

    p = subprocess.run(
        ssh_base() + ["cat", VPS_REMOTE],
        capture_output=True,
        text=True,
    )
    if p.returncode != 0:
        print(p.stderr or " ssh cat failed", file=sys.stderr)
        return p.returncode
    remote = p.stdout

    drop_pat = re.compile(
        r"^(DROPBOX_APP_KEY|DROPBOX_APP_SECRET|DROPBOX_REFRESH_TOKEN|"
        r"DROPBOX_ACCESS_TOKEN|DROPBOX_REMOTE_ROOT)="
    )

    kept: list[str] = []
    for line in remote.splitlines(keepends=True):
        s = line.lstrip("\ufeff")
        if drop_pat.match(s):
            continue
        kept.append(line)
    merged = "".join(kept).rstrip() + "\n"

    ORDER = (
        "DROPBOX_APP_KEY",
        "DROPBOX_APP_SECRET",
        "DROPBOX_REFRESH_TOKEN",
        "DROPBOX_ACCESS_TOKEN",
        "DROPBOX_REMOTE_ROOT",
    )
    block_lines = [
        "",
        "# DROPBOX_* — синхронизировано локальным скриптом (не править ключи здесь одной машиной вручную)",
    ]
    for k in ORDER:
        if k in ldb:
            block_lines.append(f"{k}={ldb[k]}")
    # Любые прочие DROPBOX_* из локального файла (редко)
    for k in sorted(ldb.keys()):
        if k.startswith("DROPBOX_") and k not in ORDER:
            block_lines.append(f"{k}={ldb[k]}")
    insert_block = "\n".join(block_lines) + "\n"

    merged = merged.rstrip() + "\n" + insert_block

    tmp = Path(__file__).with_name(".vps_airflow_merge_tmp.env")
    tmp.write_text(merged, encoding="utf-8")
    try:
        r = subprocess.run(
            [
                "scp",
                "-q",
                "-i",
                str(SSH_KEY),
                "-o",
                "StrictHostKeyChecking=accept-new",
                str(tmp),
                f"{VPS_HOST}:{VPS_REMOTE}",
            ],
            capture_output=True,
            text=True,
        )
    finally:
        tmp.unlink(missing_ok=True)

    if r.returncode != 0:
        print(r.stderr or "scp failed", file=sys.stderr)
        return r.returncode

    print(
        "OK: DROPBOX_* залиты на VPS",
        VPS_REMOTE,
        "— выполните на сервере пересборку airflow (compose up force-recreate).",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
