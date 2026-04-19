#!/bin/bash
# Однократный запуск на VPS: Docker, clone/pull, .env, prod compose.
set -euo pipefail

REPO="${REPO_URL:-https://github.com/Dezman0810/em-note.git}"
INSTALL_DIR="${INSTALL_DIR:-/opt/em-note}"
PUBLIC_IP="${PUBLIC_IP:-85.198.83.132}"

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y git curl openssl docker.io docker-compose-v2
systemctl enable --now docker

mkdir -p "$(dirname "$INSTALL_DIR")"
if [[ ! -d "$INSTALL_DIR/.git" ]]; then
  git clone --depth 1 "$REPO" "$INSTALL_DIR"
else
  git -C "$INSTALL_DIR" pull --ff-only
fi

cd "$INSTALL_DIR"
if [[ ! -f backend/.env ]]; then
  cp backend/.env.example backend/.env
fi

if grep -qE 'replace-with-long-random-secret|^JWT_SECRET_KEY=$' backend/.env; then
  JWT="$(openssl rand -hex 32)"
  sed -i "s|^JWT_SECRET_KEY=.*|JWT_SECRET_KEY=$JWT|" backend/.env
fi

sed -i 's|^DATABASE_URL=.*|DATABASE_URL=sqlite+aiosqlite:///./data/note.db|' backend/.env

CORS="http://${PUBLIC_IP},http://127.0.0.1,http://localhost,http://127.0.0.1:8080,https://em-note.ru,https://www.em-note.ru"
sed -i "s|^CORS_ORIGINS=.*|CORS_ORIGINS=${CORS}|" backend/.env

export COMPOSE_WEB_PORT=80
docker compose -f docker-compose.prod.yml up -d --build

echo "--- health ---"
curl -sS http://127.0.0.1/health
echo ""
