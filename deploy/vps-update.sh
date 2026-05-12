#!/usr/bin/env bash
# Обновление em-note на VPS после git push: подтянуть репозиторий и перезапустить веб/API.
#
# Запуск на сервере (SSH / консоль Timeweb), из каталога с клоном:
#   cd /opt/em-note    # или ваш путь
#   bash deploy/vps-update.sh
#
# Режим:
#   EM_NOTE_DEPLOY_MODE=ghcr   — образы из GitHub Container Registry (после успешного Actions)
#   EM_NOTE_DEPLOY_MODE=prod   — сборка docker-compose.prod.yml на сервере
#   EM_NOTE_DEPLOY_MODE=auto   — по умолчанию: если рядом есть .env с IMAGE_TAG= или GHCR_OWNER= → ghcr, иначе prod
#
# Переменные:
#   INSTALL_DIR — корень клона (по умолчанию текущая директория)
#   SKIP_GIT     — установите в 1, чтобы не делать git pull (только docker)
#

set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-$(pwd)}"
cd "$INSTALL_DIR" || {
  echo "Не удалось перейти в INSTALL_DIR=$INSTALL_DIR" >&2
  exit 1
}

if [ ! -f docker-compose.ghcr.yml ] || [ ! -f docker-compose.prod.yml ]; then
  echo "Ожидается корень репозитория em-note (файлы docker-compose.ghcr.yml и docker-compose.prod.yml)." >&2
  echo "Текущий каталог: $(pwd)" >&2
  exit 1
fi

MODE="${EM_NOTE_DEPLOY_MODE:-auto}"

detect_mode() {
  if [ -f .env ]; then
    if grep -qE '^(IMAGE_TAG|GHCR_OWNER)=' .env 2>/dev/null; then
      echo ghcr
      return
    fi
  fi
  # уже поднят GHCR-стек?
  if docker compose -f docker-compose.ghcr.yml ps -q web 2>/dev/null | grep -q .; then
    echo ghcr
    return
  fi
  if docker compose -f docker-compose.prod.yml ps -q web 2>/dev/null | grep -q .; then
    echo prod
    return
  fi
  echo ghcr
}

if [ "${MODE}" = "auto" ]; then
  MODE=$(detect_mode)
fi

echo "=== em-note: обновление (режим: ${MODE}) ==="
echo "Каталог: $(pwd)"

if [ "${SKIP_GIT:-0}" != "1" ]; then
  if [ ! -d .git ]; then
    echo "Нет каталога .git — пропускаю git pull (только Docker)." >&2
  else
    echo "=== git pull ==="
    git pull --ff-only
  fi
fi

case "$MODE" in
  ghcr)
    if [ ! -f .env ]; then
      echo "Нужен файл .env в корне (POSTGRES_*, COMPOSE_WEB_PORT, при необходимости GHCR_OWNER, IMAGE_TAG=main)." >&2
      exit 1
    fi
    echo "=== Важно: дождитесь в GitHub успешного workflow «Publish Docker images», иначе подтянется старый :main ==="
    echo "=== docker compose: подтянуть образы и перезапустить ==="
    # compose v2.22+: --pull always; иначе явный pull + up -d
    if docker compose up -d --help 2>&1 | grep -q '\-\-pull'; then
      docker compose -f docker-compose.ghcr.yml --env-file .env up -d --pull always
    else
      docker compose -f docker-compose.ghcr.yml --env-file .env pull
      docker compose -f docker-compose.ghcr.yml --env-file .env up -d
    fi
    echo "=== образ web (после pull) ==="
    OWN=$(grep -E '^GHCR_OWNER=' .env 2>/dev/null | cut -d= -f2- | tr -d ' \r' || true)
    ITAG=$(grep -E '^IMAGE_TAG=' .env 2>/dev/null | cut -d= -f2- | tr -d ' \r' || true)
    OWN=${OWN:-dezman0810}
    ITAG=${ITAG:-main}
    docker image inspect "ghcr.io/${OWN}/em-note-web:${ITAG}" --format 'created={{.Created}}' 2>/dev/null || true
    ;;
  prod)
    echo "=== docker compose up -d --build ==="
    docker compose -f docker-compose.prod.yml up -d --build
    ;;
  *)
    echo "Неизвестный EM_NOTE_DEPLOY_MODE=$MODE (ожидается ghcr, prod или auto)" >&2
    exit 1
    ;;
esac

PORT="${COMPOSE_WEB_PORT:-8080}"
echo "=== проверка health (http://127.0.0.1:${PORT}/health) ==="
for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS -m 3 "http://127.0.0.1:${PORT}/health" 2>/dev/null; then
    echo ""
    echo "=== готово ==="
    exit 0
  fi
  sleep 2
done
echo "(health пока не ответил — см. docker compose logs)" >&2
exit 0
