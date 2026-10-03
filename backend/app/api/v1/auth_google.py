"""Login con Google en la web (docs/rfc-001 §2.2): authorization code + PKCE resuelto en el servidor.

La cookie de sesión no cambia: sigue siendo `SameSite=Strict` y las escrituras siguen exigiendo el
encabezado CSRF. La única cookie `Lax` es la transitoria de este flujo (`panaderia_oauth`).
"""

from urllib.parse import quote, urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from app.api.deps import DB, CurrentUser
from app.core.config import get_settings
from app.core.errors import AuthError
from app.core.security import AMR_GOOGLE
from app.services import google, sesion_web
from app.services import usuarios as svc

router = APIRouter(prefix="/auth/google", tags=["Autenticación"])


def _ruta_segura(valor: str | None) -> str:
    """Solo rutas internas ("/algo"): nunca una URL de otro sitio (redirección abierta)."""
    if not valor or not valor.startswith("/") or valor.startswith("//") or "\\" in valor:
        return "/"
    return valor if not urlsplit(valor).netloc else "/"


def _fijar_cookie_oauth(response: RedirectResponse, valor: str) -> None:
    s = get_settings()
    response.set_cookie(
        s.oauth_cookie_name, valor, max_age=int(google.VIGENCIA_COOKIE_OAUTH.total_seconds()),
        httponly=True, secure=s.cookie_secure, samesite="lax", path="/",
    )


def _borrar_cookie_oauth(response: RedirectResponse) -> None:
    s = get_settings()
    response.delete_cookie(
        s.oauth_cookie_name, path="/", secure=s.cookie_secure, httponly=True, samesite="lax"
    )


@router.get("/inicio", summary="Redirige a Google para ingresar")
def inicio(volver: str = "/"):
    url, cookie = google.iniciar_flujo(volver=_ruta_segura(volver))
    respuesta = RedirectResponse(url, status_code=302)
    _fijar_cookie_oauth(respuesta, cookie)
    return respuesta


@router.get("/reautenticacion", summary="Redirige a Google para confirmar la identidad")
def reautenticacion(usuario: CurrentUser, volver: str = "/"):
    """Para la gestión sensible: Google vuelve a autenticar a la persona y el callback renueva
    `auth_time`. Exige sesión: es una navegación same-site y la cookie Strict viaja."""
    url, cookie = google.iniciar_flujo(
        volver=_ruta_segura(volver), reautenticacion=True, usuario_id=usuario.id
    )
    respuesta = RedirectResponse(url, status_code=302)
    _fijar_cookie_oauth(respuesta, cookie)
    return respuesta


def _fallo(codigo: str, datos: dict | None) -> RedirectResponse:
    """El callback es una navegación del navegador: los errores se muestran en la pantalla de ingreso
    (o en la pantalla que pidió confirmar), no como JSON."""
    if datos and datos.get("re"):
        destino = f"{_ruta_segura(datos.get('vl'))}?reauth_error={quote(codigo)}"
    else:
        destino = f"/login?error={quote(codigo)}"
    respuesta = RedirectResponse(destino, status_code=303)
    _borrar_cookie_oauth(respuesta)
    return respuesta


@router.get("/callback", summary="Vuelta desde Google")
def callback(
    request: Request, db: DB, code: str | None = None, state: str | None = None, error: str | None = None
):
    s = get_settings()
    datos: dict | None = None
    try:
        google.exigir_habilitado()
        datos = google.leer_cookie_flujo(request.cookies.get(s.oauth_cookie_name), state)
        if error or not code:
            # La persona canceló en Google, o la solicitud no trae código
            raise AuthError("Se canceló el ingreso con Google.", code="google_cancelado")
        id_token = google.intercambiar_codigo(code, datos["cv"])
        claims = google.verificar_id_token(id_token, audiencias=[s.google_client_id], nonce=datos["nc"])
        usuario = google.usuario_de_google(db, claims)
        if datos["re"] and usuario.id != datos["uid"]:
            raise AuthError(
                "La cuenta de Google no es la del usuario que inició sesión.", code="google_cuenta_distinta"
            )
        svc.liberar_pin(db, usuario)  # confirma y hace commit de la vinculación
        db.commit()
    except AuthError as e:
        db.rollback()
        return _fallo(e.code, datos)

    respuesta = RedirectResponse(_ruta_segura(datos.get("vl")), status_code=303)
    # Sesión nueva (Strict) con un CSRF nuevo; el callback es un GET, así que no aplica el doble envío
    sesion_web.emitir_sesion(respuesta, usuario, amr=AMR_GOOGLE)
    _borrar_cookie_oauth(respuesta)
    return respuesta
