import secrets
from collections.abc import Callable
from typing import Annotated

import jwt
from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AuthError, ForbiddenError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import RolEnum, Usuario

DB = Annotated[Session, Depends(get_db)]

# Solo para que Swagger ofrezca "Authorize"; el frontend usa la cookie httpOnly.
_bearer = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)

_METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}


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

    usuario = db.get(Usuario, user_id)
    if usuario is None or not usuario.activo or usuario.token_version != payload["ver"]:
        raise AuthError("Sesión inválida o expirada.")

    # Las cookies viajan solas: en métodos que modifican datos exigimos CSRF.
    # Con Authorization: Bearer no hace falta porque el navegador no lo envía solo.
    if via_cookie and request.method not in _METODOS_SEGUROS:
        _verificar_csrf(request)

    return usuario


CurrentUser = Annotated[Usuario, Depends(get_current_user)]


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

Admin = Annotated[Usuario, Depends(require_roles(RolEnum.ADMIN))]
Gestion = Annotated[Usuario, Depends(require_roles(*GESTION))]
Mostrador = Annotated[Usuario, Depends(require_roles(*MOSTRADOR))]
Produccion = Annotated[Usuario, Depends(require_roles(*PRODUCCION))]
Interno = Annotated[Usuario, Depends(require_roles(*INTERNOS))]
Repartidor = Annotated[Usuario, Depends(require_roles(*REPARTO))]
# La carga del vehículo la puede registrar la gestión o el propio repartidor
GestionORepartidor = Annotated[Usuario, Depends(require_roles(*GESTION, *REPARTO))]
