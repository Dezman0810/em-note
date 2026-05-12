#!/usr/bin/env bash
# Снять «снимок» с VPS: какой стек поднят, какой образ у web, какой коммит в клоне.
# Запуск:  cd /opt/em-note && bash deploy/vps-diagnose.sh
set -eu
echo "=== pwd ==="
pwd
echo ""
echo "=== git (последний коммит) ==="
if [ -d .git ]; then git log -1 --oneline 2>/dev/null || echo "(нет git log)"
else echo "(нет .git)"
fi
echo ""
echo "=== docker ps (все контейнеры) ==="
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null || echo "(docker недоступен)"
echo ""
echo "=== compose ghcr (если есть .env и файл) ==="
if [ -f docker-compose.ghcr.yml ] && [ -f .env ]; then
  docker compose -f docker-compose.ghcr.yml --env-file .env ps 2>/dev/null || true
else
  echo "(пропуск: нет docker-compose.ghcr.yml или .env)"
fi
echo ""
echo "=== compose prod ==="
if [ -f docker-compose.prod.yml ]; then
  docker compose -f docker-compose.prod.yml ps 2>/dev/null || true
else
  echo "(нет docker-compose.prod.yml)"
fi
echo ""
echo "=== образы em-note-web (локально) ==="
docker images --format 'table {{.Repository}}:{{.Tag}}\t{{.ID}}\t{{.CreatedSince}}' 2>/dev/null | grep -E 'em-note-web|REPOSITORY' || echo "(нет совпадений)"
echo ""
OWN=""
ITAG=""
if [ -f .env ]; then
  OWN=$(grep -E '^GHCR_OWNER=' .env 2>/dev/null | cut -d= -f2- | tr -d ' \r' || echo "")
  ITAG=$(grep -E '^IMAGE_TAG=' .env 2>/dev/null | cut -d= -f2- | tr -d ' \r' || echo "")
fi
OWN=${OWN:-dezman0810}
ITAG=${ITAG:-main}
echo "=== ожидаемый GHCR web: ghcr.io/${OWN}/em-note-web:${ITAG} ==="
docker image inspect "ghcr.io/${OWN}/em-note-web:${ITAG}" --format 'Id={{.Id}} Created={{.Created}}' 2>/dev/null || echo "(образ не скачан или другой GHCR_OWNER/IMAGE_TAG в .env)"
echo ""
echo "=== подсказка ==="
echo "Если коммит выше старый: на сервере git pull."
echo "Если образ web старый после push в main: дождитесь зелёного Actions, затем:"
echo "  EM_NOTE_DEPLOY_MODE=ghcr bash deploy/vps-update.sh"
echo "(или EM_NOTE_DEPLOY_MODE=prod если собираете только docker-compose.prod.yml)"
