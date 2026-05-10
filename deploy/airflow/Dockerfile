# Airflow + pg_dump + docker CLI (архив вложений через том Docker).
# Клиент ставим из Debian (apt), без отдельного образа docker:* с Docker Hub — меньше шансов упереться в rate limit.
FROM apache/airflow:2.10.5-python3.12
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client docker.io \
    && rm -rf /var/lib/apt/lists/*

COPY --chown=airflow:root requirements-dropbox.txt /tmp/requirements-dropbox.txt
USER airflow
RUN pip install --no-cache-dir -r /tmp/requirements-dropbox.txt \
    && rm /tmp/requirements-dropbox.txt
