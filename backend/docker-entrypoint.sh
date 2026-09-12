#!/bin/sh
set -e
cd /app

ensure_vosk_model() {
  dest="${VOSK_MODEL_PATH:-/opt/vosk-model/vosk-model-small-ru-0.22}"
  if [ -d "$dest/am" ] || [ -d "$dest/conf" ]; then
    return 0
  fi
  echo "[em-note] Модель Vosk не найдена — скачиваю vosk-model-small-ru-0.22 (~50 МБ)…"
  mkdir -p "$(dirname "$dest")"
  zip=/tmp/vosk-ru.zip
  curl -fsSL --retry 8 --retry-delay 5 --retry-all-errors \
    -o "$zip" "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"
  tmpdir=$(mktemp -d)
  unzip -q "$zip" -d "$tmpdir"
  rm -f "$zip"
  if [ -d "$tmpdir/vosk-model-small-ru-0.22" ]; then
    rm -rf "$dest"
    mv "$tmpdir/vosk-model-small-ru-0.22" "$dest"
  else
    mkdir -p "$dest"
    cp -a "$tmpdir"/. "$dest"/
  fi
  rm -rf "$tmpdir"
  echo "[em-note] Модель Vosk готова: $dest"
}

ensure_vosk_model
alembic upgrade head
exec "$@"
