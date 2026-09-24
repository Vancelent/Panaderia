import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import get_settings

# bcrypt solo considera los primeros 72 bytes; los schemas limitan el largo.
BCRYPT_MAX_BYTES = 72


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        # Hash inválido en la BD o password de más de 72 bytes
        return False


# Hash fijo para comparar cuando el usuario no existe, así el tiempo de
# respuesta no revela qué usernames son válidos.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def verify_password_dummy(plain_password: str) -> None:
    verify_password(plain_password, _DUMMY_HASH)


def create_access_token(*, user_id: int, token_version: int) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "ver": token_version,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Devuelve el payload o lanza jwt.InvalidTokenError."""
    settings = get_settings()
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["sub", "exp", "ver"]},
    )


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)
