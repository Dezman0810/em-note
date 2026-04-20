#!/usr/bin/env bash
# Полное удаление старой установки em-note на VPS и чистый деплой из Git.
# Требует: Docker + Compose, git, openssl, curl (как в remote-bootstrap.sh).
#
# На сервере:
#   curl -fsSL … | bash   ИЛИ   скопировать репозиторий и:  sudo bash deploy/vps-fresh-deploy.sh
#
# Переменные:
#   I_UNDERSTAND_WIPE=yes   — обязательно (удаляется каталог и тома БД).
#   INSTALL_DIR=/opt/em-note
#   REPO_URL=https://github.com/Dezman0810/em-note.git
#   PUBLIC_IP=1.2.3.4        — для CORS в backend/.env (опционально)
#   COMPOSE_WEB_PORT=80

set -euo pipefail

if [[ "${I_UNDERSTAND_WIPE:-}" != "yes" ]]; then
  echo "Refusing: set I_UNDERSTAND_WIPE=yes to delete the existing install and PostgreSQL volumes." >&2
  exit 1
fi

REPO_URL="${REPO_URL:-https://github.com/Dezman0810/em-note.git}"
INSTALL_DIR="${INSTALL_DIR:-/opt/em-note}"
COMPOSE_WEB_PORT="${COMPOSE_WEB_PORT:-80}"
PUBLIC_IP="${PUBLIC_IP:-}"

PARENT="$(dirname "$INSTALL_DIR")"
mkdir -p "$PARENT"

cd /

if [[ -d "$INSTALL_DIR/.git" ]] || [[ -f "$INSTALL_DIR/docker-compose.prod.yml" ]]; then
  echo "Stopping stack and removing volumes..."
  (cd "$INSTALL_DIR" && docker compose -f docker-compose.prod.yml down -v --remove-orphans) || true
fi

echo "Removing $INSTALL_DIR ..."
rm -rf "$INSTALL_DIR"

echo "Cloning $REPO_URL ..."
git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
cd "$INSTALL_DIR"

PG_PASS="$(openssl rand -hex 16)"
cat > .env <<EOF
POSTGRES_USER=postgres
POSTGRES_PASSWORD=${PG_PASS}
POSTGRES_DB=note
COMPOSE_WEB_PORT=${COMPOSE_WEB_PORT}
EOF

cp backend/.env.example backend/.env
JWT="$(openssl rand -hex 32)"
sed -i "s|^JWT_SECRET_KEY=.*|JWT_SECRET_KEY=${JWT}|" backend/.env
# Строка подключения API к Postgres задаётся в docker-compose.prod.yml (пароль из корневого .env).

if [[ -n "$PUBLIC_IP" ]]; then
  CORS="http://${PUBLIC_IP},http://127.0.0.1,http://localhost,http://127.0.0.1:8080,https://em-note.ru,https://www.em-note.ru"
  sed -i "s|^CORS_ORIGINS=.*|CORS_ORIGINS=${CORS}|" backend/.env
else
  echo "PUBLIC_IP not set; leaving CORS from .env.example — edit backend/.env if needed." >&2
fi

export COMPOSE_WEB_PORT
docker compose -f docker-compose.prod.yml up -d --build

echo "--- health (localhost) ---"
if curl -fsS "http://127.0.0.1:${COMPOSE_WEB_PORT}/health"; then
  echo ""
else
  echo "(health check failed — check: docker compose -f docker-compose.prod.yml logs)" >&2
fi

echo "--- done ---"
echo "PostgreSQL password is in $(pwd)/.env (POSTGRES_PASSWORD). Backup this file securely."
