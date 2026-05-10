# Airflow + pg_dump + docker CLI (архив вложений через том Docker).
FROM docker:27.4-cli AS dockercli
FROM apache/airflow:2.10.5-python3.12
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker

COPY --chown=airflow:root requirements-dropbox.txt /tmp/requirements-dropbox.txt
USER airflow
RUN pip install --no-cache-dir -r /tmp/requirements-dropbox.txt \
    && rm /tmp/requirements-dropbox.txt
