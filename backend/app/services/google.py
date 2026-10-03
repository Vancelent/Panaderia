"""Login con Google: OpenID Connect, authorization code + PKCE resuelto en el servidor (docs/rfc-001 §2.2).

El navegador nunca ve tokens de Google. El servidor genera `state`, `nonce` y el `code_verifier`, los
guarda en una cookie firmada de 10 minutos (la única `SameSite=Lax`: la vuelta desde Google es una
navegación entre sitios), intercambia el código y valida el `id_token`.

No hay alta automática (D11): solo entran cuentas **vinculadas** por un admin, que carga el correo en la
ficha del usuario. El primer ingreso con un correo verificado que coincida crea la vinculación por
`sub`, y desde ahí se busca por `sub`: un cambio de correo en Google no rompe el acceso.
"""

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from functools import cache
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from jwt import PyJWKClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AuthError, ConflictError
from app.models import IdentidadExterna, ProveedorIdentidadEnum, Usuario
from app.services import sesiones_moviles

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
ISSUERS = ["https://accounts.google.com", "accounts.google.com"]
VIGENCIA_COOKIE_OAUTH = timedelta(minutes=10)
_AUD_COOKIE = "oauth-panaderia"


def _error(codigo: str, mensaje: str) -> AuthError:
    return AuthError(mensaje, code=codigo)


def exigir_habilitado() -> None:
    if not get_settings().google_habilitado:
        raise AuthError("El ingreso con Google no está configurado.", code="google_no_configurado")


# ---------- Cookie transitoria del flujo ----------


def _clave_cookie() -> bytes:
    # Clave derivada: la cookie de OAuth no se puede usar como sesión ni al revés
    return hmac.new(get_settings().jwt_secret.encode("utf-8"), b"cookie-oauth", hashlib.sha256).digest()


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def iniciar_flujo(
    *, volver: str = "/", reautenticacion: bool = False, usuario_id: int | None = None
) -> tuple[str, str]:
    """Devuelve (URL de Google, valor de la cookie del flujo).

    `reautenticacion` pide a Google que vuelva a autenticar a la persona, y deja en la cookie quién la
    pidió: el callback es una navegación entre sitios y la cookie de sesión (Strict) no viaja.
    """
    exigir_habilitado()
    s = get_settings()
    state, nonce, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    ahora = datetime.now(UTC)
    cookie = jwt.encode(
        {
            "aud": _AUD_COOKIE, "st": state, "nc": nonce, "cv": verifier, "re": reautenticacion,
            "uid": usuario_id, "vl": volver, "iat": ahora, "exp": ahora + VIGENCIA_COOKIE_OAUTH,
        },
        _clave_cookie(),
        algorithm="HS256",
    )
    params = {
        "client_id": s.google_client_id,
        "redirect_uri": s.oauth_redirect_url,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "code_challenge": _challenge(verifier),
        "code_challenge_method": "S256",
        "prompt": "login" if reautenticacion else "select_account",
    }
    if s.google_hosted_domain:
        params["hd"] = s.google_hosted_domain
    return f"{AUTH_URL}?{urlencode(params)}", cookie


def leer_cookie_flujo(cookie: str | None, state_recibido: str | None) -> dict[str, Any]:
    """Verifica la cookie del flujo y que el `state` de la vuelta sea el que se generó en este navegador.

    Es lo que impide que otro sitio inicie una sesión con una cuenta ajena en el navegador de la víctima
    (el callback es un GET que inicia sesión, así que el CSRF por doble envío no aplica).
    """
    if not cookie or not state_recibido:
        raise _error("google_estado_invalido", "La solicitud de ingreso con Google no es válida o venció.")
    try:
        datos = jwt.decode(cookie, _clave_cookie(), algorithms=["HS256"], audience=_AUD_COOKIE)
    except jwt.InvalidTokenError:
        raise _error(
            "google_estado_invalido", "La solicitud de ingreso con Google no es válida o venció."
        ) from None
    if not secrets.compare_digest(str(datos["st"]), state_recibido):
        raise _error("google_estado_invalido", "La solicitud de ingreso con Google no es válida o venció.")
    return datos


# ---------- Google ----------


def intercambiar_codigo(code: str, verifier: str) -> str:
    """Canjea el código por el `id_token` (el servidor es el cliente confidencial)."""
    s = get_settings()
    try:
        r = httpx.post(
            TOKEN_URL,
            data={
                "code": code, "client_id": s.google_client_id, "client_secret": s.google_client_secret,
                "redirect_uri": s.oauth_redirect_url, "grant_type": "authorization_code",
                "code_verifier": verifier,
            },
            timeout=10,
        )
    except httpx.HTTPError:
        raise _error("google_error", "No se pudo comunicar con Google. Probá de nuevo.") from None
    if r.status_code != 200 or "id_token" not in r.json():
        raise _error("google_error", "Google rechazó el ingreso. Probá de nuevo.")
    return r.json()["id_token"]


@cache
def _jwks() -> PyJWKClient:
    return PyJWKClient(JWKS_URL, cache_keys=True, lifespan=3600, timeout=5)


def _clave_de_firma(id_token: str) -> Any:
    """Clave pública de Google con la que se firmó el token (se cachea una hora)."""
    return _jwks().get_signing_key_from_jwt(id_token).key


def verificar_id_token(id_token: str, *, audiencias: list[str], nonce: str) -> dict[str, Any]:
    """Valida firma (JWKS de Google), emisor, audiencia, vencimiento, `nonce` y correo verificado."""
    if not audiencias:
        raise _error("google_no_configurado", "El ingreso con Google no está configurado.")
    try:
        claims = jwt.decode(
            id_token,
            _clave_de_firma(id_token),
            algorithms=["RS256"],
            audience=audiencias,
            issuer=ISSUERS,
            options={"require": ["exp", "iat", "aud", "iss", "sub"]},
        )
    except jwt.PyJWTError:
        # Incluye firma, vencimiento, emisor, audiencia, algoritmo no permitido y fallos del JWKS
        raise _error("google_token_invalido", "El token de Google no es válido.") from None
    if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise _error("google_token_invalido", "El token de Google no es válido.")
    if claims.get("email_verified") not in (True, "true"):
        raise _error("google_correo_no_verificado", "Google no verificó el correo de esta cuenta.")
    dominio = get_settings().google_hosted_domain
    if dominio and claims.get("hd") != dominio:
        raise _error("google_dominio_no_permitido", f"Solo se puede ingresar con cuentas de {dominio}.")
    return claims


# ---------- Vinculación ----------


def usuario_de_google(db: Session, claims: dict[str, Any]) -> Usuario:
    """El usuario al que pertenece la cuenta de Google, vinculándola si es la primera vez.

    Si no hay una cuenta vinculada ni un usuario con ese correo, no entra nadie: tener una cuenta de
    Gmail no da acceso, y el rol lo sigue decidiendo el sistema.
    """
    sub = str(claims["sub"])
    email = str(claims.get("email", "")).strip().lower()
    identidad = db.scalar(
        select(IdentidadExterna).where(
            IdentidadExterna.proveedor == ProveedorIdentidadEnum.GOOGLE, IdentidadExterna.sub == sub
        )
    )
    if identidad is None:
        usuario = db.scalar(select(Usuario).where(Usuario.email == email)) if email else None
        if usuario is None or not usuario.activo or usuario.identidades:
            # Un usuario que ya tiene otra cuenta de Google vinculada no se vincula a una segunda
            raise _error(
                "google_no_vinculado",
                "Esta cuenta de Google no está vinculada a ningún usuario. Pedile a un administrador "
                "que cargue tu correo.",
            )
        identidad = IdentidadExterna(
            usuario=usuario, proveedor=ProveedorIdentidadEnum.GOOGLE, sub=sub, email=email
        )
        db.add(identidad)
    usuario = identidad.usuario
    if not usuario.activo:
        raise _error(
            "google_no_vinculado", "Esta cuenta de Google no está vinculada a ningún usuario activo."
        )
    identidad.email = email or identidad.email
    identidad.ultimo_uso = datetime.now(UTC)
    db.flush()
    return usuario


def desvincular(db: Session, usuario: Usuario) -> None:
    """Quita la vinculación (el admin puede volver a vincular otra cuenta). Cierra las sesiones."""
    if not usuario.identidades:
        raise ConflictError("El usuario no tiene una cuenta de Google vinculada.", code="sin_vinculacion")
    for identidad in list(usuario.identidades):
        db.delete(identidad)
    usuario.token_version += 1
    sesiones_moviles.revocar_todos(db, usuario.id)
    db.commit()
    db.refresh(usuario, ["identidades"])
