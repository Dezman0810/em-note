"""Тесты API против PostgreSQL (миграции Alembic + TRUNCATE между кейсами).

Переменная окружения TEST_DATABASE_URL переопределяет строку подключения
(по умолчанию localhost em_note_test; в контейнере api: хост db).

Один event loop: pytest-asyncio + httpx.AsyncClient (без asyncio.run + TestClient).
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401 — зарегистрировать модели
from app.config import settings
from app.database import get_db
from app.main import app

BACKEND_ROOT = Path(__file__).resolve().parents[1]

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/em_note_test",
)


def _run_alembic(url: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env={**os.environ, "DATABASE_URL": url},
        check=True,
)


@pytest.fixture(autouse=True)
def _match_admin_email_to_tagtest(monkeypatch: pytest.MonkeyPatch) -> None:
    """Регистрация tagtest@example.com даёт can_create_notes как у владельца."""
    monkeypatch.setattr(settings, "admin_email", "tagtest@example.com")


async def _truncate_user_tables(engine) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                DO $truncate$
                DECLARE
                    stmt text;
                BEGIN
                    SELECT 'TRUNCATE TABLE ' || string_agg(format('%I.%I', schemaname, tablename), ', ')
                           || ' RESTART IDENTITY CASCADE'
                    INTO stmt
                    FROM pg_tables
                    WHERE schemaname = 'public'
                      AND tablename <> 'alembic_version';
                    IF stmt IS NOT NULL THEN
                        EXECUTE stmt;
                    END IF;
                END
                $truncate$;
                """
            )
        )


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    _run_alembic(TEST_DATABASE_URL)
    engine = create_async_engine(
        TEST_DATABASE_URL,
        poolclass=NullPool,
        pool_pre_ping=True,
    )
    await _truncate_user_tables(engine)

    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with SessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=30.0) as ac:
        yield ac

    app.dependency_overrides.clear()
    await engine.dispose()
