from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Note API"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/note"

    jwt_secret_key: str = "change-me-in-production-use-long-random-string"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

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

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
