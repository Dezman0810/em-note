from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Note API"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/note"

    jwt_secret_key: str = "change-me-in-production-use-long-random-string"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7

    cors_origins: str = "http://localhost:8080,http://127.0.0.1:8080"

    # Email владельца: единственный, кто видит админку и может выдавать can_create_notes новым юзерам
    admin_email: str = "ramis.idrisov@gmail.com"

    # Optional S3 (attachments); leave empty to disable upload endpoint validation only
    s3_bucket: str = ""
    s3_region: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""

    # Локальные вложения (файлы на диске; в Docker смонтируйте том в этот каталог)
    attachments_dir: str = "/app/data/attachments"
    max_attachment_bytes: int = 25 * 1024 * 1024

    # Распознавание аудио (Vosk): путь к распакованной модели, напр. .../vosk-model-small-ru-0.22
    vosk_model_path: str = ""
    # Пусто — авто-поиск; в Docker задайте /usr/bin/ffmpeg (см. docker-compose) или полный путь на Windows
    ffmpeg_path: str = ""

    # Общий SMTP для «Отправить заметку по почте», если у пользователя не задан свой (PUT /users/me/smtp).
    # Timeweb и др.: https://timeweb.com/ru/docs/pochta/nastrojka-pochtovyh-klientov/
    smtp_relay_host: str = ""
    smtp_relay_port: int = 465
    smtp_relay_username: str = ""
    smtp_relay_password: str = ""
    # Пароль из файла (одна строка), например Docker: SMTP_RELAY_PASSWORD_FILE=/run/secrets/smtp_relay_pw
    smtp_relay_password_file: str = ""
    smtp_relay_from_address: str = ""
    # Порт 465: TLS с начала соединения (частый вариант Timeweb).
    smtp_relay_tls_immediate: bool = True
    # Порт 587: STARTTLS после EHLO (выключите tls_immediate и включите это).
    smtp_relay_start_tls: bool = False

    def smtp_relay_password_resolved(self) -> str:
        direct = (self.smtp_relay_password or "").strip()
        if direct:
            return direct
        path_raw = (self.smtp_relay_password_file or "").strip()
        if not path_raw:
            return ""
        try:
            return Path(path_raw).read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    @property
    def smtp_relay_configured(self) -> bool:
        pw = self.smtp_relay_password_resolved()
        return bool(
            self.smtp_relay_host.strip()
            and self.smtp_relay_username.strip()
            and pw
            and self.smtp_relay_from_address.strip()
        )

    @property
    def smtp_relay_needs_password(self) -> bool:
        """Хост/логин заданы, но пароль не задан ни в переменной, ни в файле."""
        return bool(
            self.smtp_relay_host.strip()
            and self.smtp_relay_username.strip()
            and self.smtp_relay_from_address.strip()
            and not self.smtp_relay_password_resolved()
        )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
