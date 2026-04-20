# Деплой (Docker)

Код на сервер попадает через **git push** → на VPS **`git pull`** и пересборка контейнеров.

## 1. DNS

У домена создайте **A** на публичный IPv4 сервера. Для `www` — отдельная **A** или CNAME, если нужен второй хост.

## 2. Сервер

Установите [Docker Engine](https://docs.docker.com/engine/install/ubuntu/) и Compose (часто уже вместе). Клонируйте репозиторий, в **`backend/.env`** скопируйте значения из `.env.example` и задайте сильный `JWT_SECRET_KEY`.

**PostgreSQL:** В `docker-compose.prod.yml` сервис `db` хранит данные в томе `em_note_pg_data`. Строка `DATABASE_URL` для API переопределяется в Compose (хост `db`); в `backend/.env` достаточно `JWT_SECRET_KEY`, `CORS_ORIGINS` и при необходимости `POSTGRES_*` на корне проекта для пароля/имени БД.

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

Регулярно делайте **pg_dump** тома PostgreSQL (`em_note_pg_data`) или снимайте логические дампы, например:

```bash
docker compose -f docker-compose.prod.yml exec -T db pg_dump -U postgres note > backup.sql
```
