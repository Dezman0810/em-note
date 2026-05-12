#!/usr/bin/env bash
# Обновить em-note на VPS по SSH с этого ПК (Git Bash / Linux / macOS).
#
#   VPS_HOST=85.198.83.132 bash deploy/remote-update-vps.sh
#
# Ключ по умолчанию: ~/.ssh/id_ed25519_timeweb (как у Timeweb).
# Опционально: VPS_USER, INSTALL_DIR, EM_NOTE_DEPLOY_MODE=ghcr|prod|auto

set -euo pipefail
VPS_HOST="${VPS_HOST:?Задайте VPS_HOST=IP_или_hostname}"
VPS_USER="${VPS_USER:-root}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519_timeweb}"
INSTALL_DIR="${INSTALL_DIR:-/opt/em-note}"
MODE="${EM_NOTE_DEPLOY_MODE:-auto}"

if [[ ! -f "$SSH_KEY" ]]; then
  echo "Нет ключа: $SSH_KEY" >&2
  exit 1
fi

if [[ "$MODE" != "auto" ]]; then
  R="cd '$INSTALL_DIR' && git pull --ff-only && EM_NOTE_DEPLOY_MODE='$MODE' bash deploy/vps-update.sh"
else
  R="cd '$INSTALL_DIR' && git pull --ff-only && bash deploy/vps-update.sh"
fi

echo "SSH $VPS_USER@$VPS_HOST (key: $SSH_KEY)"
exec ssh -i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new \
  "$VPS_USER@$VPS_HOST" "bash -lc $(printf %q "$R")"
