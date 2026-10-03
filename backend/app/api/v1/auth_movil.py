"""Autenticación de la app móvil (docs/rfc-001 §8.3): `Authorization: Bearer`, sin cookies ni CSRF.

El access token (15 min, `aud=movil`) vive solo en memoria y el refresh (30 días, rotativo) en el
almacenamiento seguro del celular. No hay PIN en la app: depende de un equipo de caja registrado.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Request

from app.api.deps import DB, Claims, CurrentUser
from app.api.v1.auth import _autenticar_con_limite, get_limiter
from app.core.config import get_settings
from app.core.errors import AuthError, TooManyRequestsError, UnprocessableError
from app.core.security import AMR_GOOGLE, AMR_PASSWORD, verify_password
from app.schemas.auth import (
    AccessMovilOut,
    MovilGoogleIn,
    MovilLoginIn,
    MovilReautenticacionIn,
    RefreshIn,
    SesionMovilOut,
)
from app.schemas.common import Mensaje
from app.services import google, sesiones_moviles
from app.services import usuarios as svc

router = APIRouter(prefix="/auth/movil", tags=["App móvil"])


def _sesion(usuario, dispositivo_id, access, refresh, segundos) -> SesionMovilOut:
    return SesionMovilOut(
        access_token=access, refresh_token=refresh, expires_in=segundos, dispositivo_id=dispositivo_id,
        usuario=usuario,
    )


@router.post("/login", response_model=SesionMovilOut)
def login(datos: MovilLoginIn, request: Request, db: DB):
    """Contraseña, con el mismo límite de intentos que la web."""
    usuario = _autenticar_con_limite(request, db, datos.username, datos.password)
    dispositivo, access, refresh, segundos = sesiones_moviles.abrir_sesion(
        db, usuario, datos.dispositivo, amr=AMR_PASSWORD
    )
    return _sesion(usuario, dispositivo.id, access, refresh, segundos)


@router.post("/google", response_model=SesionMovilOut)
def login_google(datos: MovilGoogleIn, db: DB):
    """La app obtiene el `id_token` con PKCE (`expo-auth-session`) y lo envía acá. El servidor valida
    la firma, la audiencia (los client ID de Android/iOS configurados), el `nonce` y la vinculación."""
    google.exigir_habilitado()
    claims = google.verificar_id_token(
        datos.id_token, audiencias=get_settings().google_client_ids_movil, nonce=datos.nonce
    )
    usuario = google.usuario_de_google(db, claims)
    svc.liberar_pin(db, usuario)
    dispositivo, access, refresh, segundos = sesiones_moviles.abrir_sesion(
        db, usuario, datos.dispositivo, amr=AMR_GOOGLE
    )
    return _sesion(usuario, dispositivo.id, access, refresh, segundos)


@router.post("/refresh", response_model=SesionMovilOut)
def renovar(datos: RefreshIn, db: DB):
    """Canjea el refresh por un par nuevo. Reutilizar uno viejo fuera de la ventana de gracia revoca
    toda la familia (`refresh_reutilizado`). No renueva `auth_time`."""
    usuario, dispositivo, access, refresh, segundos = sesiones_moviles.rotar(db, datos.refresh_token)
    return _sesion(usuario, dispositivo.id, access, refresh, segundos)


@router.post("/logout", response_model=Mensaje)
def logout(datos: RefreshIn, db: DB):
    sesiones_moviles.cerrar(db, datos.refresh_token)
    return {"mensaje": "Sesión cerrada."}


@router.post("/reautenticacion", response_model=AccessMovilOut)
def reautenticar(
    datos: MovilReautenticacionIn, request: Request, usuario: CurrentUser, claims: Claims, db: DB
):
    """Para la gestión sensible: vuelve a pedir contraseña o Google y devuelve un access token con
    `auth_time` nuevo (el refresh no lo renueva)."""
    if claims.get("dsp") is None:
        raise UnprocessableError("Esta sesión no es de la app móvil.", code="sesion_no_movil")
    limiter = get_limiter()
    key = f"reauth|{request.client.host if request.client else '?'}|{usuario.username}"
    if limiter.bloqueado(key):
        raise TooManyRequestsError("Demasiados intentos fallidos. Esperá unos minutos.")
    if datos.password is not None:
        if not verify_password(datos.password, usuario.hashed_password):
            limiter.registrar_fallo(key)
            raise AuthError("La contraseña no es correcta.", code="invalid_credentials")
        amr = AMR_PASSWORD
    elif datos.id_token and datos.nonce:
        google.exigir_habilitado()
        identidad = google.verificar_id_token(
            datos.id_token, audiencias=get_settings().google_client_ids_movil, nonce=datos.nonce
        )
        if google.usuario_de_google(db, identidad).id != usuario.id:
            limiter.registrar_fallo(key)
            raise AuthError("La cuenta de Google no es la del usuario.", code="google_cuenta_distinta")
        amr = AMR_GOOGLE
    else:
        raise UnprocessableError("Enviá la contraseña o un id_token de Google.", code="reauth_sin_datos")
    limiter.limpiar(key)
    svc.liberar_pin(db, usuario)
    dispositivo = sesiones_moviles.dispositivo_activo(db, claims["dsp"], usuario.id)
    access, segundos = sesiones_moviles.emitir_access(
        usuario, dispositivo, amr=amr, auth_time=datetime.now(UTC)
    )
    db.commit()
    return AccessMovilOut(access_token=access, expires_in=segundos)
