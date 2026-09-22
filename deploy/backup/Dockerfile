# Бэкап em-note: pg_dump + tar вложений + загрузка в Dropbox по расписанию.
# База — тот же образ Postgres, что и у сервиса db: версии pg_dump и сервера совпадают,
# а слои уже скачаны на сервере, так что образ почти ничего не добавляет к диску.
FROM public.ecr.aws/docker/library/postgres:16-alpine

# python3 — сама программа, tzdata — расписание по Москве, tar/gzip уже есть в базовом образе.
RUN apk add --no-cache python3 tzdata

COPY em_note_backup.py /app/em_note_backup.py

WORKDIR /app
# Базовый образ Postgres подменяет ENTRYPOINT на свой инициализатор кластера — нам он не нужен.
ENTRYPOINT ["python3", "/app/em_note_backup.py"]
CMD ["daemon"]
