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

Откройте http://localhost:8080/ (или порт из `COMPOSE_WEB_PORT`). Для SQLite в проде в `backend/.env` используйте `DATABASE_URL=sqlite+aiosqlite:///./data/note.db` — каталог `data` монтируется в постоянный том.

Подробности: [deploy/README.md](deploy/README.md).

## Git → сервер

1. Коммит и `git push` в GitHub.
2. На VPS: `git pull`, затем команда из раздела «Обновление» в `deploy/README.md`.

В репозиторий не попадают секреты и БД (см. `.gitignore`).

## Тесты (бэкенд)

```bash
cd backend
python -m venv .venv && . .venv/bin/activate  # или свой способ
pip install -r requirements-dev.txt
pytest
```

В Docker-образ API тестовые зависимости не входят — только `requirements.txt`.
