# Деплой (Docker)

Код на сервер попадает через **git push** → на VPS **`git pull`** и пересборка контейнеров.

**Чеклист разработки на Windows, коммитов и выкладки на VPS** (что писать ассистенту, какой compose): [WORKFLOW-CHECKLIST-RU.md](WORKFLOW-CHECKLIST-RU.md).

## 1. DNS

У домена создайте **A** на публичный IPv4 сервера. Для `www` — отдельная **A** или CNAME, если нужен второй хост.

## 2. Сервер

Установите [Docker Engine](https://docs.docker.com/engine/install/ubuntu/) и Compose (часто уже вместе). Клонируйте репозиторий, в **`backend/.env`** скопируйте значения из `.env.example` и задайте сильный `JWT_SECRET_KEY`.

**PostgreSQL:** В `docker-compose.prod.yml` сервис `db` хранит данные в томе `em_note_pg_data`. Строка `DATABASE_URL` для API переопределяется в Compose (хост `db`); в `backend/.env` достаточно `JWT_SECRET_KEY`, `CORS_ORIGINS` и при необходимости `POSTGRES_*` на корне проекта для пароля/имени БД.

**CORS:** добавьте в `CORS_ORIGINS` ваш публичный URL (`https://em-note.ru` и при необходимости `https://www.…`).

### Быстрый деплой через GitHub (без сборки на VPS)

Пуш в ветку **`main`** собирает образы в **GitHub Actions** и публикует их в **GHCR** (workflow `.github/workflows/publish-ghcr.yml`). На слабом VPS не запускаются **npm/vite** — только `docker compose pull` (обычно **1–2 минуты**).

1. Убедитесь, что Actions включены; после первого успешного запуска пакеты `em-note-api` и `em-note-web` появятся в разделе **Packages** репозитория / организации. Для приватного реестра на сервере выполните `docker login ghcr.io` (GitHub username + **PAT** с правом `read:packages`) или сделайте пакеты **public**.
2. В корне проекта на сервере — `.env` с `POSTGRES_*`, `COMPOSE_WEB_PORT` (в скрипте начальной установки по умолчанию **8080**, как в compose; для порта 80 на хосте укажите `80`), при необходимости `GHCR_OWNER` (по умолчанию в `docker-compose.ghcr.yml` — `dezman0810`), `IMAGE_TAG=main`.
3. Запуск: `docker compose -f docker-compose.ghcr.yml --env-file .env pull && docker compose -f docker-compose.ghcr.yml --env-file .env up -d`
4. Проверка на сервере: `curl -sS http://127.0.0.1:${COMPOSE_WEB_PORT:-8080}/health`

**Если `docker pull` для `em-note-web` отвечает `denied`:** в GitHub откройте [**Packages**](https://github.com/Dezman0810?tab=packages) → пакет **`em-note-web`** → **Package settings** → **Change package visibility** → **Public** (для `em-note-api` при необходимости то же). Либо в **Settings → Secrets → Actions** добавьте **`GH_PACKAGES_PAT`**: classic PAT с scope **`write:packages`**, затем заново запустите workflow **Publish Docker images**.

Пока `em-note-web` недоступен анонимно, на сервере используйте `docker-compose.ghcr-hybrid.yml` (API из GHCR, фронт собирается локально).

## 3. Запуск

```bash
cd /path/to/em-note
# По умолчанию в compose порт хоста 8080; для 80: export COMPOSE_WEB_PORT=80
docker compose -f docker-compose.prod.yml up -d --build
```

Проверка: `curl -sS http://127.0.0.1:8080/health` (или тот порт, что в `COMPOSE_WEB_PORT`; за reverse-proxy — по вашему домену).

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

### 5.0. Бэкап PostgreSQL перед обновлением (рекомендуется)

На VPS, из корня клона (тот же `docker-compose`, что и для запуска):

```bash
bash deploy/vps-backup-db.sh
```

Появится файл вида `backups/em_note_YYYYMMDD_HHMMSS.sql.gz`. Скопируйте его на другой диск / скачайте через `scp`. Для стека GHCR: `COMPOSE_FILE=docker-compose.ghcr.yml bash deploy/vps-backup-db.sh`.

### Одна команда на VPS (рекомендуется)

После **`git push`** в `main` подождите **успешный** workflow **Publish Docker images** в GitHub Actions (**5–15 минут**), затем на сервере:

```bash
cd /opt/em-note   # каталог с клоном репозитория
bash deploy/vps-update.sh
```

Скрипт делает **`git pull`**, затем либо **`docker compose pull` + `up`** (образы GHCR), либо **`up -d --build`** (локальная сборка `docker-compose.prod.yml`) — в зависимости от `EM_NOTE_DEPLOY_MODE` или авто-определения (см. комментарии в `deploy/vps-update.sh`).

Принудительно только GHCR или только prod:

```bash
EM_NOTE_DEPLOY_MODE=ghcr bash deploy/vps-update.sh
EM_NOTE_DEPLOY_MODE=prod bash deploy/vps-update.sh
```

Если в репозитории на сервере старый скрипт, сначала: `git pull --ff-only`, потом снова `bash deploy/vps-update.sh`.

### Обновление с вашего ПК по SSH (ключ Timeweb)

На **Windows** в PowerShell из корня клона `em-note` (подставьте IP VPS):

```powershell
.\deploy\remote-update-vps.ps1 -VpsHost 85.198.83.132
```

По умолчанию используется ключ **`%USERPROFILE%\.ssh\id_ed25519_timeweb`**. Другой ключ: `-SshKey "D:\keys\my_ed25519"`. Режим деплоя: `-DeployMode ghcr` или `prod` (по умолчанию `auto`, как в `vps-update.sh`). Пользователь SSH: `-VpsUser root`. Каталог на сервере: `-InstallDir /opt/em-note`.

В **Git Bash / Linux**:

```bash
export VPS_HOST=85.198.83.132
export SSH_KEY="$HOME/.ssh/id_ed25519_timeweb"   # по умолчанию так же
bash deploy/remote-update-vps.sh
```

На VPS в каталоге проекта должен быть **клон по SSH или HTTPS с `git pull`**, и уже один раз настроенный `.env` и Docker, как в разделах выше. Первый коннект: при необходимости примите fingerprint хоста (в скрипте используется `StrictHostKeyChecking=accept-new`).

**Ничего не меняется в браузере:** на сервере выполните **`bash deploy/vps-diagnose.sh`** и пришлите вывод (или сами проверьте: дата образа `em-note-web`, совпадает ли режим GHCR vs prod). Частые причины: не выполнялся `docker pull` / скрипт; Actions ещё не зелёный; на VPS другой каталог или используется только `docker-compose.prod.yml` без `--build`.

**HTTP 413 при импорте схемы Excalidraw (~1 MB и больше):** импорт кладёт сцену в JSON заметки; при сохранении уходит большой **`PATCH /api/notes/…`**. Если лимита тела запроса недостаточно, nginx (или другой reverse proxy **перед** Docker) отдаёт **413**. В образе **`em-note-web`** в **`deploy/nginx/docker-prod.conf`** задан **`client_max_body_size 100m`** и таймауты для **`/api/`**. Если 413 сохраняется после обновления образа и перезапуска контейнеров, проверьте **лимиты у хостинг-провайдера**: у панелей иногда свой nginx с телом порядка **`1m`** — его нужно увеличить для этого сайта или проксировать напрямую на порт контейнера.

### Сборка на сервере (`docker-compose.prod.yml`)

```bash
git pull --ff-only
docker compose -f docker-compose.prod.yml up -d --build
```

### Образы из GHCR (`docker-compose.ghcr.yml`)

После **`git push`** в `main` GitHub Actions **пересобирает** `em-note-api` и `em-note-web` и обновляет тег **`main`**. Если на VPS сразу сделать только `docker compose pull`, можно скачать **ещё старый** `web`, пока workflow не закончился — новый UI не появится.

1. Убедитесь в репозитории: **Actions** → последний run **Publish Docker images** — **успешно**.
2. На сервере (вручную, если не используете `vps-update.sh`):

```bash
cd /opt/em-note   # или ваш путь
git pull --ff-only
docker compose -f docker-compose.ghcr.yml --env-file .env pull
docker compose -f docker-compose.ghcr.yml --env-file .env up -d
```

В `docker-compose.ghcr.yml` уже задано `name: em-note-prod` — отдельный флаг `-p` обычно не нужен. При сомнениях повторите `pull` + `up -d` через несколько минут после зелёного Actions. В браузере сделайте **жёсткое обновление** (Ctrl+F5).

## 6. HTTPS

В `docker-compose.prod.yml` только HTTP. Типичные варианты: отдельный хостовый Nginx/Caddy с Let’s Encrypt перед контейнерами, или облачный прокси с TLS.

Если на VPS уже стоит **системный Nginx**, который проксирует 80/443 на `127.0.0.1:8080` (Docker `em-note-prod-web`), в нём нужно **`client_max_body_size`**, иначе при больших JSON (импорт Excalidraw) будет **413** — дефолт nginx порядка **1m**. Образец с **`100m`**: [deploy/nginx/vps-host-em-note-proxy.conf](nginx/vps-host-em-note-proxy.conf) (путь на сервере типично `/etc/nginx/sites-available/em-note-proxy`, затем `nginx -t` и **`systemctl reload nginx`**).

## 7. Бэкапы

Регулярно делайте **pg_dump** тома PostgreSQL (`em_note_pg_data`) или снимайте логические дампы, например:

```bash
docker compose -f docker-compose.prod.yml exec -T db pg_dump -U postgres note > backup.sql
```

## 8. Airflow → Dropbox (ежедневный бэкап + восстановление через UI)

В репозитории отдельный compose: `docker-compose.airflow.yml` (метаданные Airflow в SQLite, без второго Postgres). На VPS подключается к сети прод-стека файлом `docker-compose.airflow.vps.yml`.

Пошагово: **[deploy/airflow/README.md](airflow/README.md)** и **[deploy/airflow/DROPBOX-STEPS-RU.txt](airflow/DROPBOX-STEPS-RU.txt)**.
