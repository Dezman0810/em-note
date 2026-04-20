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

## 4. Полная переустановка (снести проект и БД, развернуть заново)

На **чистом Ubuntu** с Docker/Compose (или после `deploy/remote-bootstrap.sh` один раз установите пакеты как там).

С этой машины без SSH-ключа к VPS автоматически подключиться нельзя — зайдите по SSH в панели Timeweb или вставьте команду в «Консоль» сервера.

На сервере (подставьте свой публичный IP вместо `ВАШ_IP` для CORS):

```bash
export I_UNDERSTAND_WIPE=yes
export PUBLIC_IP=ВАШ_IP
curl -fsSL https://raw.githubusercontent.com/Dezman0810/em-note/main/deploy/vps-fresh-deploy.sh | bash
```

Либо уже после `git clone`:

```bash
cd /opt/em-note   # или путь к клону
sudo I_UNDERSTAND_WIPE=yes PUBLIC_IP=ВАШ_IP bash deploy/vps-fresh-deploy.sh
```

Скрипт удаляет каталог установки и **том PostgreSQL** (`down -v`), клонирует репозиторий заново, создаёт корневой `.env` с случайным паролем БД и запускает `docker-compose.prod.yml`. Пароль хранится в `/opt/em-note/.env` — сохраните его.

## 5. Обновление (без сноса данных)

```bash
git pull --ff-only
docker compose -f docker-compose.prod.yml up -d --build
```

## 6. HTTPS

В `docker-compose.prod.yml` только HTTP. Типичные варианты: отдельный хостовый Nginx/Caddy с Let’s Encrypt перед контейнерами, или облачный прокси с TLS.

## 7. Бэкапы

Регулярно делайте **pg_dump** тома PostgreSQL (`em_note_pg_data`) или снимайте логические дампы, например:

```bash
docker compose -f docker-compose.prod.yml exec -T db pg_dump -U postgres note > backup.sql
```
