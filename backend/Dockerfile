FROM public.ecr.aws/docker/library/python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl ca-certificates unzip \
    && rm -rf /var/lib/apt/lists/* \
    && ffmpeg -version

# Русская модель Vosk (~50 MB) вне /app: при dev volume ./backend:/app каталог приложения подменяется, /opt — нет.
RUN mkdir -p /opt/vosk-model \
    && curl -fsSL -o /tmp/vosk-ru.zip "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip" \
    && unzip -q /tmp/vosk-ru.zip -d /opt/vosk-model \
    && rm /tmp/vosk-ru.zip \
    && test -d /opt/vosk-model/vosk-model-small-ru-0.22

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    VOSK_MODEL_PATH=/opt/vosk-model/vosk-model-small-ru-0.22

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Windows checkout часто даёт CRLF в .sh — sed убирает \r до запуска.
RUN sed -i 's/\r$//' /app/docker-entrypoint.sh && chmod +x /app/docker-entrypoint.sh

EXPOSE 8000

# Явный /bin/sh — иначе на Windows CRLF в shebang даёт «no such file or directory» в Linux.
ENTRYPOINT ["/bin/sh", "/app/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
