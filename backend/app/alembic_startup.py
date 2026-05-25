"""Один раз при старте приложения поднимает схему БД через Alembic (локальный uvicorn без Docker)."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


def alembic_upgrade_head_at_startup() -> None:
    """
    Прогон `alembic upgrade head` из каталога backend.

    Пропуск: SKIP_ALEMBIC_AT_STARTUP=1 (pytest). На POSIX — flock между воркерами.
    """
    if os.environ.get("SKIP_ALEMBIC_AT_STARTUP", "").strip().lower() in ("1", "true", "yes", "on"):
        logger.info("Пропуск Alembic при старте (SKIP_ALEMBIC_AT_STARTUP)")
        return

    backend_root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "DATABASE_URL": settings.database_url}
    lock_path = backend_root / ".alembic_lifespan_startup.lock"

    def _run() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(backend_root),
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )

    try:
        if sys.platform == "win32":
            result = _run()
        else:
            import fcntl

            lock_path.touch(exist_ok=True)
            with open(lock_path, "r+", encoding="utf-8") as lf:
                fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
                result = _run()
    except subprocess.TimeoutExpired as e:
        logger.exception("Alembic: таймаут")
        raise RuntimeError("alembic upgrade head: таймаут") from e
    except OSError as e:
        logger.exception("Alembic: не удалось запустить subprocess или flock")
        raise RuntimeError("alembic upgrade head: ошибка запуска") from e

    if result.returncode != 0:
        logger.error(
            "alembic upgrade head завершился с кодом %s\nstdout:\n%s\nstderr:\n%s",
            result.returncode,
            result.stdout,
            result.stderr,
        )
        raise RuntimeError(
            "Не удалось применить миграции БД (alembic upgrade head). "
            "Проверьте DATABASE_URL и логи выше."
        )

    combined = ((result.stdout or "") + (result.stderr or "")).strip()
    if combined:
        logger.info("Alembic upgrade head: %s", combined[:2000])
