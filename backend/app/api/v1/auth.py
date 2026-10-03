from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import DB, Claims, CurrentUser, Gestion, GestionFuerte, verificar_origen
from app.core.config import get_settings
from app.core.errors import AuthError, ForbiddenError, TooManyRequestsError
from app.core.rate_limit import LoginRateLimiter
from app.core.security import (
    AMR_FUERTES,
    AMR_PASSWORD,
    AMR_PIN,
    create_access_token,
    verify_password,
)
from app.models import Terminal, Usuario
from app.schemas.auth import (
    DispositivoOut,
    MeOut,
    MetodosOut,
    PinLoginIn,
    ReautenticacionIn,
    SesionOut,
    TerminalActualOut,
    TerminalCreate,
    TerminalOut,
    TerminalUpdate,
)
from app.schemas.common import Mensaje
from app.schemas.usuarios import CambioPassword, LoginIn, UsuarioOut
from app.services import sesion_web, sesiones_moviles, terminales
from app.services import usuarios as svc

router = APIRouter(prefix="/auth", tags=["Autenticación"])


@lru_cache
def get_limiter() -> LoginRateLimiter:
    s = get_settings()
    return LoginRateLimiter(s.login_max_intentos, s.login_ventana_segundos)


@lru_cache
def get_pin_limiter() -> LoginRateLimiter:
    """Intentos de PIN por IP y equipo. Más holgado que el de contraseña: el PIN de cada persona ya se
    bloquea a los 5 fallos, y un error de una cajera no debería frenar a las demás en la misma caja."""
    s = get_settings()
    return LoginRateLimiter(s.pin_max_fallos * 3, s.login_ventana_segundos)


def _ip(request: Request) -> str:
    return request.client.host if request.client else "?"


def _autenticar_con_limite(request: Request, db, username: str, password: str) -> Usuario:
    limiter = get_limiter()
    key = f"{_ip(request)}|{username.lower()}"
    if limiter.bloqueado(key):
        raise TooManyRequestsError("Demasiados intentos fallidos. Esperá unos minutos.")
    try:
        usuario = svc.autenticar(db, username.lower(), password)
    except Exception:
        limiter.registrar_fallo(key)
        raise
    limiter.limpiar(key)
    return usuario


def _terminal_de_la_cookie(request: Request, db) -> Terminal | None:
    return terminales.desde_secreto(db, request.cookies.get(get_settings().terminal_cookie_name))


def _sesion_out(claims: dict) -> SesionOut:
    limite = get_settings().reautenticacion_minutos * 60
    auth_time = int(claims["auth_time"])
    reciente = datetime.now(UTC).timestamp() - auth_time <= limite
    return SesionOut(
        metodo=claims["amr"],
        auth_time=datetime.fromtimestamp(auth_time, UTC),
        fuerte=claims["amr"] in AMR_FUERTES and reciente,
        terminal_id=claims.get("trm"),
    )


# ---------- Qué ofrece la pantalla de ingreso ----------


@router.get("/metodos", response_model=MetodosOut)
def metodos(request: Request, db: DB):
    """Opciones de ingreso para este equipo: Google (si está configurado) y, si el equipo está
    registrado como caja o cuadra, las personas que pueden entrar con PIN."""
    terminal = _terminal_de_la_cookie(request, db)
    actual = None
    if terminal is not None:
        actual = TerminalActualOut(
            id=terminal.id, nombre=terminal.nombre, tipo=terminal.tipo,
            usuarios=terminales.usuarios_con_pin(db, terminal),
        )
    return MetodosOut(google=get_settings().google_habilitado, terminal=actual)


# ---------- Ingreso ----------


@router.post("/login", response_model=UsuarioOut)
def login(datos: LoginIn, request: Request, response: Response, db: DB):
    usuario = _autenticar_con_limite(request, db, datos.username, datos.password)
    sesion_web.emitir_sesion(response, usuario, amr=AMR_PASSWORD)
    return usuario


@router.post("/pin", response_model=UsuarioOut)
def login_con_pin(datos: PinLoginIn, request: Request, response: Response, db: DB):
    """Ingreso con PIN, solo desde un equipo registrado (cookie de terminal válida).

    Todavía no hay sesión, así que no hay CSRF por doble envío: se exige el `Origin` propio y la cookie
    del terminal. La sesión dura hasta cerrar el turno o `PIN_SESION_MINUTOS` y no habilita la gestión.
    """
    verificar_origen(request, estricto=True)
    terminal = _terminal_de_la_cookie(request, db)
    if terminal is None:
        raise ForbiddenError(
            "Este equipo no está registrado para ingresar con PIN.", code="terminal_no_registrada"
        )
    limiter = get_pin_limiter()
    key = f"pin|{_ip(request)}|{terminal.id}"
    if limiter.bloqueado(key):
        raise TooManyRequestsError("Demasiados intentos fallidos. Esperá unos minutos.")
    try:
        usuario = terminales.iniciar_sesion_pin(db, terminal, datos.usuario_id, datos.pin)
    except AuthError:
        limiter.registrar_fallo(key)
        raise
    limiter.limpiar(key)
    sesion_web.emitir_sesion(
        response, usuario, amr=AMR_PIN, terminal_id=terminal.id, minutos=get_settings().pin_sesion_minutos
    )
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
    sesion_web.borrar_sesion(response)
    return {"mensaje": "Sesión cerrada."}


# ---------- Sesión actual ----------


@router.get("/me", response_model=MeOut)
def me(usuario: CurrentUser, claims: Claims):
    return MeOut(
        id=usuario.id, username=usuario.username, nombre=usuario.nombre, email=usuario.email,
        rol=usuario.rol, activo=usuario.activo, sesion=_sesion_out(claims),
    )


@router.post("/reautenticacion", response_model=MeOut)
def reautenticar(
    datos: ReautenticacionIn, request: Request, response: Response, usuario: CurrentUser, db: DB
):
    """Confirma la identidad con la contraseña y renueva `auth_time`, sin perder la pantalla.

    Es lo que desbloquea la gestión sensible a una sesión con PIN o a una sesión vieja
    (`401 reautenticacion_requerida`). Con Google se hace por `GET /auth/google/reautenticacion`.
    """
    limiter = get_limiter()
    key = f"reauth|{_ip(request)}|{usuario.username}"
    if limiter.bloqueado(key):
        raise TooManyRequestsError("Demasiados intentos fallidos. Esperá unos minutos.")
    if not verify_password(datos.password, usuario.hashed_password):
        limiter.registrar_fallo(key)
        raise AuthError("La contraseña no es correcta.", code="invalid_credentials")
    limiter.limpiar(key)
    svc.liberar_pin(db, usuario)
    sesion_web.emitir_sesion(response, usuario, amr=AMR_PASSWORD)
    ahora = datetime.now(UTC)
    return MeOut(
        id=usuario.id, username=usuario.username, nombre=usuario.nombre, email=usuario.email,
        rol=usuario.rol, activo=usuario.activo,
        sesion=SesionOut(metodo=AMR_PASSWORD, auth_time=ahora, fuerte=True),
    )


@router.post("/cambiar-password", response_model=UsuarioOut)
def cambiar_password(datos: CambioPassword, usuario: CurrentUser, response: Response, db: DB):
    usuario = svc.cambiar_password(db, usuario, datos.password_actual, datos.password_nueva)
    # El cambio invalida los tokens anteriores; emitimos uno nuevo para esta sesión.
    sesion_web.emitir_sesion(response, usuario, amr=AMR_PASSWORD)
    return usuario


@router.post("/cerrar-sesiones", response_model=Mensaje)
def cerrar_todas_las_sesiones(usuario: CurrentUser, response: Response, db: DB):
    svc.cerrar_sesiones(db, usuario)
    sesion_web.borrar_sesion(response)
    return {"mensaje": "Se cerraron todas las sesiones."}


# ---------- Terminales (equipos registrados para PIN) ----------


@router.post("/terminales", response_model=TerminalOut, status_code=status.HTTP_201_CREATED)
def registrar_terminal(datos: TerminalCreate, response: Response, usuario: GestionFuerte, db: DB):
    """"Registrar este equipo como caja": el secreto viaja en la cookie del equipo (httpOnly, larga
    duración) y en la base solo queda su hash."""
    terminal, secreto = terminales.registrar(db, usuario, datos.nombre, datos.tipo)
    sesion_web.fijar_terminal(response, secreto)
    return terminal


@router.get("/terminales", response_model=list[TerminalOut])
def listar_terminales(_: Gestion, db: DB):
    return terminales.listar(db)


@router.patch("/terminales/{terminal_id}", response_model=TerminalOut)
def actualizar_terminal(terminal_id: int, datos: TerminalUpdate, _: GestionFuerte, db: DB):
    """Desactivar un equipo invalida de inmediato todas las sesiones PIN emitidas en él."""
    return terminales.actualizar(db, terminal_id, datos.nombre, datos.activo)


# ---------- Mis dispositivos (app móvil) ----------


@router.get("/dispositivos", response_model=list[DispositivoOut])
def mis_dispositivos(usuario: CurrentUser, db: DB):
    return sesiones_moviles.listar(db, usuario.id)


@router.delete("/dispositivos/{dispositivo_id}", response_model=DispositivoOut)
def cerrar_sesion_de_dispositivo(dispositivo_id: int, usuario: CurrentUser, db: DB):
    return sesiones_moviles.revocar(db, dispositivo_id, usuario_id=usuario.id)
