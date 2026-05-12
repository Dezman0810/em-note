#!/usr/bin/env bash
# Снимок PostgreSQL перед обновлением em-note на VPS (том em_note_pg_data не трогаем).
#
# Запуск из корня клона на сервере:
#   bash deploy/vps-backup-db.sh
#
# Переменные:
#   COMPOSE_FILE  — docker-compose.prod.yml | docker-compose.ghcr.yml (по умолчанию prod)
#   BACKUP_DIR    — каталог для .sql.gz (по умолчанию ./backups)
#
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
INSTALL_DIR="${INSTALL_DIR:-$(pwd)}"
cd "$INSTALL_DIR"

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "Нет файла $COMPOSE_FILE в $(pwd)" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"
STAMP=$(date +%Y%m%d_%H%M%S)
OUT="$BACKUP_DIR/em_note_${STAMP}.sql.gz"

# Подставить POSTGRES_* из корневого .env (если есть)
set -a
if [ -f .env ]; then
  # shellcheck disable=SC1091
  . ./.env
fi
set +a

PGU="${POSTGRES_USER:-postgres}"
PGD="${POSTGRES_DB:-note}"

echo "=== pg_dump → $OUT (compose: $COMPOSE_FILE) ==="
docker compose -f "$COMPOSE_FILE" exec -T db pg_dump -U "$PGU" --no-owner --no-acl "$PGD" | gzip >"$OUT"

echo "Готово: $OUT ($(du -h "$OUT" | cut -f1))"
echo "Восстановление (пример, на пустую БД): gunzip -c $OUT | docker compose -f $COMPOSE_FILE exec -T db psql -U $PGU -d $PGD"
