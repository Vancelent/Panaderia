"""Cookies de la sesión web: sesión (httpOnly), CSRF (legible por JS) y terminal (httpOnly, larga)."""

from datetime import datetime

from fastapi import Response

from app.core.config import get_settings
from app.core.security import AMR_PASSWORD, create_access_token, new_csrf_token
from app.models import Usuario

TERMINAL_MAX_AGE = 60 * 60 * 24 * 365 * 5  # el equipo queda registrado hasta que un admin lo desactive


def emitir_sesion(
    response: Response,
    usuario: Usuario,
    *,
    amr: str = AMR_PASSWORD,
    auth_time: datetime | None = None,
    terminal_id: int | None = None,
    minutos: int | None = None,
) -> None:
    """Emite la cookie de sesión (SameSite=Strict) y un CSRF nuevo.

    Es la misma sesión sin importar cómo entró la persona: el resto del sistema solo ve el claim `amr`.
    """
    s = get_settings()
    max_age = (minutos or s.jwt_expire_minutes) * 60
    token = create_access_token(
        user_id=usuario.id, token_version=usuario.token_version, amr=amr, auth_time=auth_time,
        terminal_id=terminal_id, minutos=minutos,
    )
    response.set_cookie(
        s.cookie_name, token, max_age=max_age, httponly=True,
        secure=s.cookie_secure, samesite="strict", path="/",
    )
    # Legible por JS a propósito (double-submit CSRF); no da acceso por sí sola.
    response.set_cookie(
        s.csrf_cookie_name, new_csrf_token(), max_age=max_age, httponly=False,
        secure=s.cookie_secure, samesite="strict", path="/",
    )


def borrar_sesion(response: Response) -> None:
    s = get_settings()
    # Los atributos tienen que coincidir con los de set_cookie: una cookie `__Host-` borrada sin
    # `Secure` es rechazada por el navegador y la sesión no se cierra.
    response.delete_cookie(
        s.cookie_name, path="/", secure=s.cookie_secure, httponly=True, samesite="strict"
    )
    response.delete_cookie(
        s.csrf_cookie_name, path="/", secure=s.cookie_secure, httponly=False, samesite="strict"
    )


def fijar_terminal(response: Response, secreto: str) -> None:
    s = get_settings()
    response.set_cookie(
        s.terminal_cookie_name, secreto, max_age=TERMINAL_MAX_AGE, httponly=True,
        secure=s.cookie_secure, samesite="strict", path="/",
    )
