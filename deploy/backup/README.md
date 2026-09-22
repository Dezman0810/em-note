# Ежедневный бэкап em-note (замена Airflow)

Сервис `backup` в прод-стеке делает то же, что делал DAG `em_note_db_backup`:
раз в сутки снимает `pg_dump` базы и `tar.gz` каталога вложений и кладёт обе копии
в Dropbox по пути `{DROPBOX_REMOTE_ROOT}/{ГГГГ-ММ-ДД}/`.

Отличия от Airflow:

| | Airflow | этот сервис |
|---|---|---|
| Память | ~500 МБ (scheduler + webserver) | ~15 МБ |
| Доступ к `docker.sock` | нужен, чтобы собрать архив вложений | не нужен: том примонтирован |
| Метабаза, веб-интерфейс | есть | нет, расписание — цикл ожидания |
| Файлы больше 145 МБ | загрузка падала | загружаются сессией по частям |

## Переменные окружения

Задаются в `/opt/em-note/.env` рядом с `docker-compose.ghcr.yml` (compose подставит их сам).

| Переменная | По умолчанию | Смысл |
|---|---|---|
| `DROPBOX_REFRESH_TOKEN` | — | Долгоживущий токен (рекомендуется) |
| `DROPBOX_APP_KEY` | — | Ключ приложения Dropbox |
| `DROPBOX_APP_SECRET` | — | Секрет приложения Dropbox |
| `DROPBOX_ACCESS_TOKEN` | — | Альтернатива трём предыдущим; живёт ~4 часа |
| `DROPBOX_REMOTE_ROOT` | `/` | Папка в Dropbox. Для приложения с доступом только к своей папке корень API — уже она, `/Apps/...` писать не нужно |
| `BACKUP_TIME` | `03:30` | Время ежедневного запуска |
| `BACKUP_TZ` | `Europe/Moscow` | Часовой пояс расписания |
| `BACKUP_KEEP_DAYS` | `0` | Удалять копии старше N дней. `0` — не удалять ничего |
| `BACKUP_ON_START` | `0` | `1` — сделать копию сразу при старте контейнера |

Доступ к базе и вложениям сервис получает из `docker-compose.ghcr.yml`
(`PGHOST`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`, `ATTACHMENTS_DIR`) — менять не нужно.

Токены Dropbox берутся те же, что использовал Airflow: они лежат в
`deploy/airflow/airflow.env`. Перенесите оттуда `DROPBOX_*` в `/opt/em-note/.env`.

## Проверка

```bash
cd /opt/em-note
docker compose -f docker-compose.ghcr.yml up -d --build backup
docker compose -f docker-compose.ghcr.yml logs -f backup      # видно время следующего запуска
docker compose -f docker-compose.ghcr.yml exec backup python3 /app/em_note_backup.py backup
docker compose -f docker-compose.ghcr.yml exec backup python3 /app/em_note_backup.py list
```

## Восстановление

Заменяет базу и **полностью очищает** каталог вложений перед распаковкой архива —
как и DAG `em_note_restore_from_dropbox`.

```bash
# последняя копия за день
docker compose -f docker-compose.ghcr.yml exec backup \
  python3 /app/em_note_backup.py restore 2026-09-22

# конкретные файлы, если за день их несколько
docker compose -f docker-compose.ghcr.yml exec backup \
  python3 /app/em_note_backup.py restore 2026-09-22 note_20260922_033001.sql attachments_20260922_033001.tar.gz

docker compose -f docker-compose.ghcr.yml restart api
```

## Выключить Airflow

Когда новый бэкап отработает хотя бы раз:

```bash
cd /opt/em-note
docker compose -f docker-compose.airflow.yml -f docker-compose.airflow.vps.yml down
docker image prune -a
```

Освободится примерно 500 МБ оперативной памяти.
