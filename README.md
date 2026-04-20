# em-note

Заметки, папки, метки, общий доступ, почта. **FastAPI** + **Vue 3** + **TipTap**. Запуск и dev — через **Docker**; один репозиторий для ПК и для VPS.

## Быстрый старт (разработка)

1. Клонируйте репозиторий.
2. `cp backend/.env.example backend/.env` — задайте `JWT_SECRET_KEY` и при необходимости `DATABASE_URL`, `CORS_ORIGINS`.
3. В корне проекта:

```bash
docker compose up --build -d
docker compose logs -f
```

- UI: http://localhost:5173/
- API: http://localhost:8000/docs  

Фронт в контейнере проксирует `/api` на сервис `api` (`API_PROXY_TARGET` в Compose).

## Продакшен (как на VPS)

Собранный фронт + Nginx и API в одном стеке:

```bash
export COMPOSE_WEB_PORT=80   # локально по умолчанию 8080, если переменная не задана
docker compose -f docker-compose.prod.yml up -d --build
```

Откройте http://localhost:8080/ (или порт из `COMPOSE_WEB_PORT`). В стеке поднимается **PostgreSQL** (данные в томе `em_note_pg_data`); строка подключения для контейнера API задаётся в `docker-compose.prod.yml` (хост `db`).

Подробности: [deploy/README.md](deploy/README.md).

## Git → сервер

1. Коммит и `git push` в GitHub.
2. На VPS: `git pull`, затем команда из раздела «Обновление» в `deploy/README.md`.

В репозиторий не попадают секреты и БД (см. `.gitignore`).

## Тесты (бэкенд)

Нужен **PostgreSQL** и база **`em_note_test`** (после первого `docker compose up` она создаётся скриптом в `deploy/postgres/docker-entrypoint-initdb.d`). По умолчанию тесты подключаются к `postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/em_note_test`.

```bash
cd backend
python -m venv .venv && . .venv/bin/activate  # или свой способ
pip install -r requirements-dev.txt
pytest
```

В Docker-образ API тестовые зависимости не входят — только `requirements.txt`. Запуск тестов в контейнере: `docker compose exec -e TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/em_note_test api sh -c "cd /app && pip install -q -r requirements-dev.txt && pytest"`.
