from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import DB, CurrentUser
from app.core.config import get_settings
from app.core.errors import TooManyRequestsError
from app.core.rate_limit import LoginRateLimiter
from app.core.security import create_access_token, new_csrf_token
from app.models import Usuario
from app.schemas.common import Mensaje
from app.schemas.usuarios import CambioPassword, LoginIn, UsuarioOut
from app.services import usuarios as svc

router = APIRouter(prefix="/auth", tags=["Autenticación"])


@lru_cache
def get_limiter() -> LoginRateLimiter:
    s = get_settings()
    return LoginRateLimiter(s.login_max_intentos, s.login_ventana_segundos)


def _autenticar_con_limite(request: Request, db, username: str, password: str) -> Usuario:
    limiter = get_limiter()
    ip = request.client.host if request.client else "?"
    key = f"{ip}|{username.lower()}"
    if limiter.bloqueado(key):
        raise TooManyRequestsError("Demasiados intentos fallidos. Esperá unos minutos.")
    try:
        usuario = svc.autenticar(db, username.lower(), password)
    except Exception:
        limiter.registrar_fallo(key)
        raise
    limiter.limpiar(key)
    return usuario


def _set_session_cookies(response: Response, usuario: Usuario) -> None:
    s = get_settings()
    max_age = s.jwt_expire_minutes * 60
    token = create_access_token(user_id=usuario.id, token_version=usuario.token_version)
    response.set_cookie(
        s.cookie_name, token, max_age=max_age, httponly=True,
        secure=s.cookie_secure, samesite="strict", path="/",
    )
    # Legible por JS a propósito (double-submit CSRF); no da acceso por sí sola.
    response.set_cookie(
        s.csrf_cookie_name, new_csrf_token(), max_age=max_age, httponly=False,
        secure=s.cookie_secure, samesite="strict", path="/",
    )


def _clear_session_cookies(response: Response) -> None:
    s = get_settings()
    # Los atributos tienen que coincidir con los de set_cookie: una cookie `__Host-` borrada sin
    # `Secure` es rechazada por el navegador y la sesión no se cierra.
    response.delete_cookie(
        s.cookie_name, path="/", secure=s.cookie_secure, httponly=True, samesite="strict"
    )
    response.delete_cookie(
        s.csrf_cookie_name, path="/", secure=s.cookie_secure, httponly=False, samesite="strict"
    )


@router.post("/login", response_model=UsuarioOut)
def login(datos: LoginIn, request: Request, response: Response, db: DB):
    usuario = _autenticar_con_limite(request, db, datos.username, datos.password)
    _set_session_cookies(response, usuario)
    return usuario


@router.post("/token", include_in_schema=True, summary="Login OAuth2 (solo Swagger / clientes API)")
def token(form: Annotated[OAuth2PasswordRequestForm, Depends()], request: Request, db: DB):
    usuario = _autenticar_con_limite(request, db, form.username, form.password)
    return {
        "access_token": create_access_token(user_id=usuario.id, token_version=usuario.token_version),
        "token_type": "bearer",
    }


@router.post("/logout", response_model=Mensaje)
def logout(response: Response):
    # No exige sesión válida: siempre limpia las cookies del navegador.
    _clear_session_cookies(response)
    return {"mensaje": "Sesión cerrada."}


@router.get("/me", response_model=UsuarioOut)
def me(usuario: CurrentUser):
    return usuario


@router.post("/cambiar-password", response_model=UsuarioOut)
def cambiar_password(datos: CambioPassword, usuario: CurrentUser, response: Response, db: DB):
    usuario = svc.cambiar_password(db, usuario, datos.password_actual, datos.password_nueva)
    # El cambio invalida los tokens anteriores; emitimos uno nuevo para esta sesión.
    _set_session_cookies(response, usuario)
    return usuario


@router.post("/cerrar-sesiones", response_model=Mensaje)
def cerrar_todas_las_sesiones(usuario: CurrentUser, response: Response, db: DB):
    svc.cerrar_sesiones(db, usuario)
    _clear_session_cookies(response)
    return {"mensaje": "Se cerraron todas las sesiones."}
