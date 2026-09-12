from datetime import datetime, timedelta, timezone
from typing import Any
import secrets

import bcrypt
from jose import JWTError, jwt

from app.config import settings


def generate_temporary_password(length: int = 12) -> str:
    """Одноразовый пароль для сброса админом. Старый хеш восстановить нельзя."""
    alphabet = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    n = max(8, min(32, int(length)))
    return "".join(secrets.choice(alphabet) for _ in range(n))


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {"sub": subject, "exp": expire}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


def token_subject(token: str) -> str | None:
    try:
        payload = decode_token(token)
        sub = payload.get("sub")
        return str(sub) if sub else None
    except JWTError:
        return None
