#!/usr/bin/env sh
# Одноразовый деплой на VPS: git pull, .env, docker compose ghcr pull + up.
set -eu
REPO_URL="${REPO_URL:-https://github.com/Dezman0810/em-note.git}"
INSTALL_DIR="${INSTALL_DIR:-/opt/em-note}"
PUBLIC_IP="${PUBLIC_IP:-85.198.83.132}"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git curl openssl ca-certificates docker.io docker-compose-v2

systemctl enable --now docker

mkdir -p "$(dirname "$INSTALL_DIR")"
if [ ! -d "$INSTALL_DIR/.git" ]; then
  git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
else
  git -C "$INSTALL_DIR" pull --ff-only
fi
cd "$INSTALL_DIR"

if ! swapon --show 2>/dev/null | grep -q swapfile; then
  fallocate -l 2G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=2048
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q /swapfile /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

if [ ! -f .env ]; then
  PG_PASS="$(openssl rand -hex 16)"
  {
    echo "POSTGRES_USER=postgres"
    echo "POSTGRES_PASSWORD=${PG_PASS}"
    echo "POSTGRES_DB=note"
    echo "COMPOSE_WEB_PORT=8080"
    echo "GHCR_OWNER=dezman0810"
    echo "IMAGE_TAG=main"
  } > .env
fi

set -a
# shellcheck disable=SC1091
. ./.env
set +a

if [ ! -f backend/.env ]; then
  cp backend/.env.example backend/.env
  JWT="$(openssl rand -hex 32)"
  sed -i "s|^JWT_SECRET_KEY=.*|JWT_SECRET_KEY=${JWT}|" backend/.env
fi

CORS="http://${PUBLIC_IP},http://${PUBLIC_IP}:8080,http://127.0.0.1,http://127.0.0.1:8080,http://localhost,https://em-note.ru,https://www.em-note.ru"
if grep -q '^CORS_ORIGINS=' backend/.env; then
  sed -i "s|^CORS_ORIGINS=.*|CORS_ORIGINS=${CORS}|" backend/.env
else
  echo "CORS_ORIGINS=${CORS}" >> backend/.env
fi

echo "=== docker compose pull (GHCR) ==="
docker compose -f docker-compose.ghcr.yml --env-file .env pull

echo "=== docker compose up ==="
docker compose -f docker-compose.ghcr.yml --env-file .env up -d

echo "=== wait for API ==="
for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
  if curl -fsS -m 2 "http://127.0.0.1:${COMPOSE_WEB_PORT:-8080}/health" >/dev/null 2>&1; then
    echo "health OK"
    curl -fsS "http://127.0.0.1:${COMPOSE_WEB_PORT:-8080}/health" || true
    echo ""
    break
  fi
  sleep 2
done

docker compose -f docker-compose.ghcr.yml ps
echo "=== done ==="
