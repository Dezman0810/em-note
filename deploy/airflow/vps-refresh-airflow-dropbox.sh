#!/usr/bin/env bash
# На VPS: git pull + пересоздать Airflow после синхронизации DROPBOX_* в airflow.env.
set -euo pipefail
cd /opt/em-note
git pull --ff-only
if [ -f deploy/strip-backend-env-bom.py ]; then
  python3 deploy/strip-backend-env-bom.py deploy/airflow/airflow.env || true
fi
docker compose -f docker-compose.airflow.yml -f docker-compose.airflow.vps.yml \
  --env-file deploy/airflow/airflow.env up -d --force-recreate airflow-scheduler airflow-webserver
sleep 12
docker compose -f docker-compose.airflow.yml exec -T airflow-scheduler python -c \
  "import os,dropbox; c=dropbox.Dropbox(oauth2_refresh_token=os.environ['DROPBOX_REFRESH_TOKEN'].strip(),app_key=os.environ['DROPBOX_APP_KEY'],app_secret=os.environ['DROPBOX_APP_SECRET']); c.users_get_current_account(); print('dropbox_ok')"
echo "=== Airflow UI: http://$(hostname -I | awk '{print $1}'):8088 ==="
