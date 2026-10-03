import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from functools import cache

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


# Métodos de autenticación (claim `amr`)
AMR_PASSWORD = "pwd"
AMR_GOOGLE = "google"
AMR_PIN = "pin"
# Los que cuentan como "autenticación fuerte" para la gestión sensible (docs/rfc-001 §2.4)
AMR_FUERTES = (AMR_PASSWORD, AMR_GOOGLE)

AUD_WEB = "web"
AUD_MOVIL = "movil"


def create_access_token(
    *,
    user_id: int,
    token_version: int,
    amr: str = AMR_PASSWORD,
    auth_time: datetime | None = None,
    audience: str = AUD_WEB,
    dispositivo_id: int | None = None,
    terminal_id: int | None = None,
    minutos: int | None = None,
) -> str:
    """JWT de sesión. `amr` dice cómo entró la persona y `auth_time` cuándo se autenticó por
    última vez con contraseña o Google (un refresh o un PIN no lo renuevan)."""
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "ver": token_version,
        "iat": now,
        "exp": now + timedelta(minutes=minutos or settings.jwt_expire_minutes),
        "amr": amr,
        "auth_time": int((auth_time or now).timestamp()),
        "aud": audience,
    }
    if dispositivo_id is not None:
        payload["dsp"] = dispositivo_id
    if terminal_id is not None:
        payload["trm"] = terminal_id
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Devuelve el payload o lanza jwt.InvalidTokenError.

    Un token emitido antes de la autenticación híbrida (sin `amr`, `auth_time` ni `aud`) se
    interpreta como una sesión web con contraseña iniciada en su `iat`.
    """
    settings = get_settings()
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        # La audiencia la verifica get_current_user según por dónde llegó el token
        options={"require": ["sub", "exp", "ver"], "verify_aud": False},
    )
    payload.setdefault("amr", AMR_PASSWORD)
    payload.setdefault("auth_time", int(payload.get("iat", 0)))
    payload.setdefault("aud", AUD_WEB)
    return payload


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


# ---------- Tokens opacos (refresh, secreto del terminal) ----------


def nuevo_token_opaco() -> str:
    """256 bits aleatorios. Solo el hash se guarda en la base."""
    return secrets.token_urlsafe(32)


def hash_token_opaco(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ---------- PIN ----------


def _pepper() -> bytes:
    settings = get_settings()
    # En desarrollo y tests puede faltar PIN_PEPPER: se deriva del secreto del JWT. En producción es
    # obligatorio (Settings lo exige) y no se reutiliza ese secreto.
    if settings.pin_pepper:
        return settings.pin_pepper.encode("utf-8")
    return hmac.new(settings.jwt_secret.encode("utf-8"), b"pin-pepper-desarrollo", hashlib.sha256).digest()


def _pin_preparado(pin: str) -> bytes:
    # HMAC-SHA256 con el pepper del servidor, y recién ahí bcrypt: robar la base no alcanza para
    # probar los 10.000 PIN posibles de 4 dígitos
    return hmac.new(_pepper(), pin.encode("utf-8"), hashlib.sha256).hexdigest().encode("ascii")


def hash_pin(pin: str) -> str:
    return bcrypt.hashpw(_pin_preparado(pin), bcrypt.gensalt()).decode("utf-8")


def verify_pin(pin: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_pin_preparado(pin), hashed.encode("utf-8"))
    except ValueError:
        return False


@cache
def _dummy_pin_hash() -> str:
    return hash_pin("0000")


def verify_pin_dummy(pin: str) -> None:
    """Igual costo que un PIN real, para que el tiempo no revele quién tiene PIN."""
    verify_pin(pin, _dummy_pin_hash())
