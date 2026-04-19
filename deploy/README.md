# Деплой (Docker)

Код на сервер попадает через **git push** → на VPS **`git pull`** и пересборка контейнеров.

## 1. DNS

У домена создайте **A** на публичный IPv4 сервера. Для `www` — отдельная **A** или CNAME, если нужен второй хост.

## 2. Сервер

Установите [Docker Engine](https://docs.docker.com/engine/install/ubuntu/) и Compose (часто уже вместе). Клонируйте репозиторий, в **`backend/.env`** скопируйте значения из `.env.example` и задайте сильный `JWT_SECRET_KEY`.

**SQLite в проде:** чтобы файл БД жил в томе `em_note_api_data`, в `.env` укажите:

```env
DATABASE_URL=sqlite+aiosqlite:///./data/note.db
```

**CORS:** добавьте в `CORS_ORIGINS` ваш публичный URL (`https://em-note.ru` и при необходимости `https://www.…`).

## 3. Запуск

```bash
cd /path/to/em-note
export COMPOSE_WEB_PORT=80   # локально можно оставить 8080 по умолчанию
docker compose -f docker-compose.prod.yml up -d --build
```

Проверка: `curl -sS http://127.0.0.1/health` (на сервере с портом 80 — по вашему домену).

## 4. Обновление

```bash
git pull --ff-only
docker compose -f docker-compose.prod.yml up -d --build
```

## 5. HTTPS

В `docker-compose.prod.yml` только HTTP. Типичные варианты: отдельный хостовый Nginx/Caddy с Let’s Encrypt перед контейнерами, или облачный прокси с TLS.

## 6. Бэкапы

При SQLite скопируйте том или файл из каталога данных контейнера (`/app/data/note.db` внутри API-контейнера при указанном `DATABASE_URL` выше).
