# Note

Веб-приложение: заметки, папки, метки, общий доступ, почта. Стек: **FastAPI** (async SQLAlchemy) + **Vue 3** + **TipTap**.

## Требования

- Python 3.11+ (рекомендуется)
- Node.js 20+ и npm
- Для PostgreSQL — отдельно установленный сервер (опционально; по умолчанию можно **SQLite**)

## Клонирование и первый запуск

```bash
git clone <URL-вашего-репозитория>.git
cd Note
```

### Бэкенд

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# Отредактируйте .env: JWT_SECRET_KEY и при необходимости DATABASE_URL
.\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000
```

В `.env` для быстрого старта без PostgreSQL оставьте строку из примера:

`DATABASE_URL=sqlite+aiosqlite:///./note.db`

### Фронтенд (другой терминал)

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Откройте **http://127.0.0.1:5173/** — запросы к `/api` проксируются на порт 8000 (см. `frontend/vite.config.ts`).

### Скрипты Windows

Из корня проекта:

- `scripts\start-dev.ps1` — два окна: API и Vite  
- `scripts\restart-dev.ps1` — освобождает порты 8000 и 5173, затем то же самое  

## Публикация на GitHub

1. Создайте **пустой** репозиторий на GitHub (без README, если уже есть в проекте).
2. В корне `Note`:

```powershell
git remote add origin https://github.com/<ваш-логин>/<имя-репо>.git
git branch -M main
git push -u origin main
```

Для входа используйте **Personal Access Token** (Settings → Developer settings) или GitHub CLI (`gh auth login`).

## Что не попадает в Git

Секреты и артефакты перечислены в `.gitignore`: `backend/.env`, виртуальное окружение, `node_modules`, локальные БД и т.д. На новом ПК скопируйте `backend/.env` вручную или снова создайте из `.env.example`.
