import secrets
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import urlsplit

import jwt
from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AuthError, ForbiddenError
from app.core.security import AMR_FUERTES, AUD_MOVIL, AUD_WEB, decode_access_token
from app.db.session import get_db
from app.models import Dispositivo, RolEnum, Terminal, Usuario

DB = Annotated[Session, Depends(get_db)]

# Solo para que Swagger ofrezca "Authorize"; el frontend usa la cookie httpOnly.
_bearer = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)

_METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}


def _hosts_permitidos(request: Request) -> set[str]:
    settings = get_settings()
    hosts = {request.headers.get("host", "").lower()}
    for origen in settings.origenes_permitidos:
        hosts.add(urlsplit(origen if "//" in origen else f"//{origen}").netloc.lower())
    return {h for h in hosts if h}


def verificar_origen(request: Request, *, estricto: bool = False) -> None:
    """Defensa en profundidad contra CSRF: una escritura hecha desde otro sitio se rechaza.

    Compara el encabezado `Origin` (o `Sec-Fetch-Site`) con el host propio. Los clientes que no son
    navegadores (curl, tests) no envían ninguno de los dos y pasan, salvo con `estricto=True`
    (login con PIN, que todavía no tiene sesión y por eso exige `Origin`).
    """
    origen = request.headers.get("origin")
    if origen:
        if origen == "null" or urlsplit(origen).netloc.lower() not in _hosts_permitidos(request):
            raise ForbiddenError("Origen no permitido.", code="origen_invalido")
        return
    sitio = request.headers.get("sec-fetch-site")
    if sitio and sitio not in ("same-origin", "none"):
        raise ForbiddenError("Origen no permitido.", code="origen_invalido")
    if estricto and not sitio:
        raise ForbiddenError("Falta el origen de la solicitud.", code="origen_invalido")


def _verificar_csrf(request: Request) -> None:
    """Double-submit: el header debe coincidir con la cookie CSRF (no httpOnly)."""
    settings = get_settings()
    cookie = request.cookies.get(settings.csrf_cookie_name)
    header = request.headers.get(settings.csrf_header_name)
    if not cookie or not header or not secrets.compare_digest(cookie, header):
        raise ForbiddenError("Token CSRF ausente o inválido.", code="csrf_failed")


def get_current_user(
    request: Request,
    db: DB,
    bearer_token: Annotated[str | None, Depends(_bearer)],
) -> Usuario:
    settings = get_settings()
    token = request.cookies.get(settings.cookie_name)
    via_cookie = token is not None
    if not via_cookie:
        token = bearer_token
    if not token:
        raise AuthError("No autenticado.")

    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, ValueError, KeyError):
        raise AuthError("Sesión inválida o expirada.") from None

    # Una cookie solo vale si la emitió la web; un Bearer puede ser de la web (Swagger) o de la app
    if payload["aud"] not in ((AUD_WEB,) if via_cookie else (AUD_WEB, AUD_MOVIL)):
        raise AuthError("Sesión inválida o expirada.")

    usuario = db.get(Usuario, user_id)
    if usuario is None or not usuario.activo or usuario.token_version != payload["ver"]:
        raise AuthError("Sesión inválida o expirada.")

    # Revocar un equipo (terminal) o un celular (dispositivo) cierra todas las sesiones emitidas en él
    terminal_id = payload.get("trm")
    if terminal_id is not None:
        terminal = db.get(Terminal, terminal_id)
        if terminal is None or not terminal.activo:
            raise AuthError("Sesión inválida o expirada.")
    dispositivo_id = payload.get("dsp")
    if dispositivo_id is not None:
        dispositivo = db.get(Dispositivo, dispositivo_id)
        if dispositivo is None or dispositivo.revocado_en is not None or dispositivo.usuario_id != usuario.id:
            raise AuthError("Sesión inválida o expirada.")

    # Las cookies viajan solas: en métodos que modifican datos exigimos origen propio y CSRF.
    # Con Authorization: Bearer no hace falta porque el navegador no lo envía solo.
    if via_cookie and request.method not in _METODOS_SEGUROS:
        verificar_origen(request)
        _verificar_csrf(request)

    request.state.auth = payload
    return usuario


CurrentUser = Annotated[Usuario, Depends(get_current_user)]


def get_auth_claims(request: Request, _: CurrentUser) -> dict:
    """Cómo y cuándo se autenticó la sesión actual (claims `amr`, `auth_time`, `trm`, `dsp`)."""
    return request.state.auth


Claims = Annotated[dict, Depends(get_auth_claims)]


def exigir_auth_fuerte(claims: dict) -> None:
    """Gestión sensible (docs/rfc-001 §2.4): contraseña o Google, iniciada hace poco.

    Una sesión con PIN, o una más vieja que `REAUTENTICACION_MINUTOS`, recibe
    `401 reautenticacion_requerida` y la pantalla ofrece confirmar sin perder el trabajo.
    """
    limite = get_settings().reautenticacion_minutos * 60
    reciente = datetime.now(UTC).timestamp() - int(claims["auth_time"]) <= limite
    if claims["amr"] not in AMR_FUERTES or not reciente:
        raise AuthError(
            "Para esta acción confirmá tu identidad con tu contraseña o con Google.",
            code="reautenticacion_requerida",
        )


def require_roles(*roles: RolEnum) -> Callable[..., Usuario]:
    permitidos = set(roles)

    def _dep(usuario: CurrentUser) -> Usuario:
        if usuario.rol not in permitidos:
            raise ForbiddenError("No tenés permisos para esta acción.")
        return usuario

    return _dep


# Grupos de roles de uso frecuente
GESTION = (RolEnum.ADMIN, RolEnum.ENCARGADA)
MOSTRADOR = (RolEnum.ADMIN, RolEnum.ENCARGADA, RolEnum.VENDEDORA)
PRODUCCION = (RolEnum.ADMIN, RolEnum.ENCARGADA, RolEnum.PANADERO)
REPARTO = (RolEnum.REPARTIDOR,)
# Todo el personal del local: el repartidor solo opera sobre su hoja de ruta
INTERNOS = (RolEnum.ADMIN, RolEnum.ENCARGADA, RolEnum.VENDEDORA, RolEnum.PANADERO)
TODOS = tuple(RolEnum)


def require_auth_fuerte(*roles: RolEnum) -> Callable[..., Usuario]:
    """Como `require_roles`, y además exige autenticación fuerte reciente (ver `exigir_auth_fuerte`)."""
    permitidos = set(roles)

    def _dep(usuario: CurrentUser, claims: Claims) -> Usuario:
        if usuario.rol not in permitidos:
            raise ForbiddenError("No tenés permisos para esta acción.")
        exigir_auth_fuerte(claims)
        return usuario

    return _dep


Admin = Annotated[Usuario, Depends(require_roles(RolEnum.ADMIN))]
Gestion = Annotated[Usuario, Depends(require_roles(*GESTION))]
Mostrador = Annotated[Usuario, Depends(require_roles(*MOSTRADOR))]
Produccion = Annotated[Usuario, Depends(require_roles(*PRODUCCION))]
Interno = Annotated[Usuario, Depends(require_roles(*INTERNOS))]
Repartidor = Annotated[Usuario, Depends(require_roles(*REPARTO))]
# Gestión sensible: usuarios, precios, descuentos, ajustes, cierre de turnos ajenos, correcciones de
# cuenta corriente y terminales. Una sesión con PIN, o una vieja, debe reautenticarse primero.
AdminFuerte = Annotated[Usuario, Depends(require_auth_fuerte(RolEnum.ADMIN))]
GestionFuerte = Annotated[Usuario, Depends(require_auth_fuerte(*GESTION))]
# La carga del vehículo la puede registrar la gestión o el propio repartidor
GestionORepartidor = Annotated[Usuario, Depends(require_roles(*GESTION, *REPARTO))]
