#!/bin/sh
# Точка входа для сервиса web в docker-compose.yml (Vite dev).
# Полный npm ci при смене package-lock.json — не остаётся «битый» node_modules после git pull.
set -e
cd /app

STAMP_FILE=node_modules/.em-note-lock-stamp
if [ -f package-lock.json ]; then
  WANT_SIG=$(sha256sum package-lock.json | cut -d' ' -f1)
else
  WANT_SIG=no-package-lock
fi

GOT_SIG=""
if [ -f "$STAMP_FILE" ]; then
  GOT_SIG=$(cat "$STAMP_FILE" || true)
fi

if [ "$GOT_SIG" != "$WANT_SIG" ] || [ ! -f node_modules/@tiptap/extension-table/package.json ]; then
  echo "em-note web: установка зависимостей (lock или node_modules не совпадают с репозиторием)..."
  rm -rf node_modules
  if [ -f package-lock.json ]; then
    npm ci
  else
    npm install
  fi
  mkdir -p node_modules
  printf '%s' "$WANT_SIG" > "$STAMP_FILE"
fi

npm install --no-audit --no-fund

if [ ! -f node_modules/@tiptap/extension-table/package.json ]; then
  echo "Ошибка: не установлен @tiptap/extension-table." >&2
  echo "Убедитесь, что frontend/package.json и frontend/package-lock.json из одного коммита с репозиторием." >&2
  exit 1
fi

exec npm run dev -- --host 0.0.0.0 --port 5173
