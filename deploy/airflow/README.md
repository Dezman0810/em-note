# Airflow: бэкап и восстановление em-note в Dropbox

- **DAG `em_note_db_backup`** — ежедневно: `pg_dump` + архив тома вложений → Dropbox.
- **DAG `em_note_restore_from_dropbox`** — ручной запуск: скачать из Dropbox → `psql` + распаковка в том вложений.

Подробно по Dropbox: [DROPBOX-STEPS-RU.txt](./DROPBOX-STEPS-RU.txt).

## Локально (Windows / dev)

Из корня репозитория:

```powershell
copy deploy\airflow\airflow.env.example deploy\airflow\airflow.env
# Заполните секреты Dropbox и при необходимости строки восстановления
docker compose up -d db
docker compose -f docker-compose.airflow.yml up -d --build
```

UI: http://localhost:8088  

В `airflow.env` для Postgres обычно: `host.docker.internal:5432`.  
Том вложений: `em-note_em_note_attachments` (если `docker compose` без `-p`).

## VPS (прод рядом с em-note)

1. Клон репозитория, `deploy/airflow/airflow.env` из примера (файл с секретами **не** в git).

2. Узнайте **имя Docker-сети** стека с БД (после `docker compose … up` прод-стека):

   ```bash
   docker network ls | grep -E 'em-note|note'
   ```

   Часто: `em-note-prod_default` при запуске с `-p em-note-prod` (см. deploy/README.md для GHCR).

3. Поднимите Airflow **с вторым compose-файлом**, чтобы контейнеры были в той же сети, что и сервис `db`:

   ```bash
   cd /opt/em-note   # каталог клона
   export EM_NOTE_DOCKER_NETWORK=em-note-prod_default   # если другое — подставьте
   docker compose -f docker-compose.airflow.yml -f docker-compose.airflow.vps.yml --env-file deploy/airflow/airflow.env up -d --build
   ```

4. В `deploy/airflow/airflow.env`:

   - `AIRFLOW_CONN_POSTGRES_EM_NOTE=postgresql://postgres:ПАРОЛЬ_ИЗ_КОРНЕВОГО_.env@db:5432/note`  
     (тот же пользователь/БД, что в `docker-compose.prod.yml` / GHCR.)
   - `EM_NOTE_ATTACHMENTS_VOLUME` — из `docker volume ls`, обычно `em-note-prod_em_note_attachments`.

5. UI по умолчанию: `http://ВАШ_VPS:8088`. Желательно не открывать порт в мир без пароля / VPN; можно повесить reverse-proxy с auth или слушать только `127.0.0.1` (правка `ports` в `docker-compose.airflow.yml`).

6. Метаданные Airflow — SQLite в томе `em_note_airflow_sqlite` (отдельного Postgres для Airflow нет).

## Обновление DAG / образа на VPS

```bash
git pull --ff-only
docker compose -f docker-compose.airflow.yml -f docker-compose.airflow.vps.yml --env-file deploy/airflow/airflow.env up -d --build
```

Если второй файл не нужен (редко: БД только на localhost с проброшенным портом), используйте только `docker-compose.airflow.yml` и `host.docker.internal` / IP хоста в URI.
