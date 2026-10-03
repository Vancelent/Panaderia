"""Sesiones de la app móvil (docs/rfc-001 §8.3): access de 15 min, refresh opaco rotativo con detección de
reutilización y ventana de gracia, reautenticación y revocación por dispositivo."""

import hashlib
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.security import decode_access_token
from app.db.session import SessionLocal
from app.main import app
from app.models import RefreshToken, RolEnum, Usuario
from tests.conftest import PASSWORD, Cliente, crear_usuario, login
from tests.google_falso import CLIENT_ANDROID, CLIENT_ID, CLIENT_IOS, id_token

API = "/api/v1"
M = f"{API}/auth/movil"
CEL = {"nombre": "Moto G del reparto", "plataforma": "Android"}


def _entrar(username="repa", password=PASSWORD, cel=CEL):
    c = Cliente(app)
    r = c.post(f"{M}/login", json={"username": username, "password": password, "dispositivo": cel})
    return r


def _auth(access: str) -> dict:
    return {"Authorization": f"Bearer {access}"}


def _sesion(rol=RolEnum.REPARTIDOR, username="repa"):
    crear_usuario(username, rol)
    r = _entrar(username)
    assert r.status_code == 200, r.text
    return r.json()


def _yo(access: str):
    return Cliente(app).get(f"{API}/auth/me", headers=_auth(access))


def _renovar(refresh: str):
    return Cliente(app).post(f"{M}/refresh", json={"refresh_token": refresh})


# ---------- Ingreso ----------


def test_login_movil_emite_access_corto_y_refresh_opaco():
    s = _sesion()
    assert s["token_type"] == "bearer" and s["expires_in"] == 15 * 60
    claims = decode_access_token(s["access_token"])
    assert claims["aud"] == "movil" and claims["amr"] == "pwd" and claims["dsp"] == s["dispositivo_id"]
    assert claims["exp"] - claims["iat"] == 15 * 60
    assert s["usuario"]["username"] == "repa" and "hashed_password" not in str(s)
    assert len(s["refresh_token"]) >= 40  # 256 bits
    assert "set-cookie" not in _entrar().headers  # la app no usa cookies
    me = _yo(s["access_token"])
    assert me.status_code == 200 and me.json()["sesion"]["metodo"] == "pwd"


def test_el_refresh_se_guarda_solo_como_hash():
    s = _sesion()
    with SessionLocal() as db:
        rt = db.scalar(select(RefreshToken))
        assert rt.token_hash == hashlib.sha256(s["refresh_token"].encode()).hexdigest()
        assert s["refresh_token"] not in rt.token_hash and rt.token_hash != s["refresh_token"]
        assert rt.metodo == "pwd" and rt.usado_en is None


def test_credenciales_invalidas_y_limite_de_intentos():
    crear_usuario("repa", RolEnum.REPARTIDOR)
    for _ in range(5):
        r = _entrar(password="incorrecta-123")
        assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_credentials"
    assert _entrar().status_code == 429  # mismo límite que la web
    assert _entrar("nadie").status_code in (401, 429)


def test_el_login_movil_valida_el_dispositivo():
    crear_usuario("repa", RolEnum.REPARTIDOR)
    r = Cliente(app).post(f"{M}/login", json={"username": "repa", "password": PASSWORD, "dispositivo": {"nombre": ""}})
    assert r.status_code == 422


def test_un_usuario_inactivo_no_entra():
    crear_usuario("repa", RolEnum.REPARTIDOR)
    with SessionLocal() as db:
        db.scalar(select(Usuario)).activo = False
        db.commit()
    assert _entrar().status_code == 401


# ---------- Rotación ----------


def test_cada_refresh_emite_un_par_nuevo_y_el_viejo_ya_no_rota_tras_la_gracia():
    s = _sesion()
    r = _renovar(s["refresh_token"])
    assert r.status_code == 200, r.text
    nuevo = r.json()
    assert nuevo["refresh_token"] != s["refresh_token"] and nuevo["dispositivo_id"] == s["dispositivo_id"]
    assert _yo(nuevo["access_token"]).status_code == 200
    with SessionLocal() as db:
        viejo, actual = db.scalars(select(RefreshToken).order_by(RefreshToken.id)).all()
        assert viejo.usado_en is not None and viejo.reemplazado_por_id == actual.id
        assert viejo.familia_id == actual.familia_id  # misma familia
    assert _renovar(nuevo["refresh_token"]).status_code == 200  # el nuevo sigue rotando


def test_reintentar_dentro_de_la_ventana_de_gracia_se_tolera():
    """Con señal intermitente la respuesta de la rotación se puede perder: la app reintenta con el token
    viejo y no se la expulsa."""
    s = _sesion()
    primera = _renovar(s["refresh_token"])
    assert primera.status_code == 200
    segunda = _renovar(s["refresh_token"])  # perdió la respuesta anterior y reintenta con el viejo
    assert segunda.status_code == 200
    assert segunda.json()["refresh_token"] != primera.json()["refresh_token"]
    # Ambos hijos son válidos (la familia sigue viva)
    assert _renovar(primera.json()["refresh_token"]).status_code == 200
    assert _renovar(segunda.json()["refresh_token"]).status_code == 200


def test_la_gracia_no_se_prolonga_con_cada_reintento():
    s = _sesion()
    _renovar(s["refresh_token"])
    with SessionLocal() as db:
        db.scalar(select(RefreshToken).order_by(RefreshToken.id)).usado_en = datetime.now(UTC) - timedelta(seconds=25)
        db.commit()
    assert _renovar(s["refresh_token"]).status_code == 200  # a los 25 s todavía se tolera
    with SessionLocal() as db:
        db.scalar(select(RefreshToken).order_by(RefreshToken.id)).usado_en = datetime.now(UTC) - timedelta(seconds=40)
        db.commit()
    assert _renovar(s["refresh_token"]).status_code == 401


def test_reutilizar_un_refresh_fuera_de_la_gracia_revoca_toda_la_familia():
    s = _sesion()
    hijo = _renovar(s["refresh_token"]).json()
    nieto = _renovar(hijo["refresh_token"]).json()
    with SessionLocal() as db:  # pasaron más de 30 s desde que se usó el primero
        primero = db.scalar(select(RefreshToken).order_by(RefreshToken.id))
        primero.usado_en = datetime.now(UTC) - timedelta(minutes=5)
        db.commit()
    robo = _renovar(s["refresh_token"])  # alguien con una copia vieja
    assert robo.status_code == 401 and robo.json()["error"]["code"] == "refresh_reutilizado"
    # Toda la familia quedó revocada, incluido el token más nuevo (el de la persona legítima)
    assert _renovar(nieto["refresh_token"]).status_code == 401
    assert _renovar(hijo["refresh_token"]).status_code == 401
    with SessionLocal() as db:
        assert all(rt.revocado_en is not None for rt in db.scalars(select(RefreshToken)))


def test_refresh_desconocido_vencido_o_de_dispositivo_revocado():
    s = _sesion()
    assert _renovar("x" * 43).status_code == 401
    assert _renovar("corto").status_code == 422
    with SessionLocal() as db:
        db.scalar(select(RefreshToken)).expira_en = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    r = _renovar(s["refresh_token"])
    assert r.status_code == 401 and r.json()["error"]["code"] == "refresh_invalido"


def test_el_refresh_no_renueva_auth_time_y_la_gestion_pide_reautenticar():
    crear_usuario("jefe", RolEnum.ADMIN)
    s = _entrar("jefe").json()
    with SessionLocal() as db:  # la persona se autenticó hace 40 minutos
        db.scalar(select(RefreshToken)).auth_time = datetime.now(UTC) - timedelta(minutes=40)
        db.commit()
    nuevo = _renovar(s["refresh_token"]).json()
    assert abs(decode_access_token(nuevo["access_token"])["auth_time"] - (time.time() - 40 * 60)) < 10
    nuevo_usuario = {"username": "nuevo", "rol": "Vendedora", "password": "clave-segura-123"}
    r = Cliente(app).post(f"{API}/usuarios", json=nuevo_usuario, headers=_auth(nuevo["access_token"]))
    assert r.status_code == 401 and r.json()["error"]["code"] == "reautenticacion_requerida"

    mala = Cliente(app).post(f"{M}/reautenticacion", json={"password": "incorrecta-123"},
                             headers=_auth(nuevo["access_token"]))
    assert mala.status_code == 401
    ok = Cliente(app).post(f"{M}/reautenticacion", json={"password": PASSWORD}, headers=_auth(nuevo["access_token"]))
    assert ok.status_code == 200 and ok.json()["expires_in"] == 15 * 60
    fresco = ok.json()["access_token"]
    assert Cliente(app).post(f"{API}/usuarios", json=nuevo_usuario, headers=_auth(fresco)).status_code == 201
    # ...pero al renovar de nuevo se vuelve a la autenticación vieja: hay que repetirla
    otra = _renovar(nuevo["refresh_token"]).json()
    r = Cliente(app).post(f"{API}/usuarios", json={**nuevo_usuario, "username": "otro"},
                          headers=_auth(otra["access_token"]))
    assert r.status_code == 401


def test_reautenticar_pide_datos_y_solo_sirve_para_sesiones_de_la_app():
    s = _sesion()
    assert Cliente(app).post(f"{M}/reautenticacion", json={}, headers=_auth(s["access_token"])).status_code == 422
    # Un token de la web (sin dispositivo) no es una sesión móvil
    crear_usuario("web", RolEnum.ADMIN)
    web = login("web")
    r = web.post(f"{M}/reautenticacion", json={"password": PASSWORD})
    assert r.status_code == 422 and r.json()["error"]["code"] == "sesion_no_movil"


# ---------- Revocación ----------


def test_cerrar_sesion_revoca_el_dispositivo_y_es_idempotente():
    s = _sesion()
    assert _yo(s["access_token"]).status_code == 200
    r = Cliente(app).post(f"{M}/logout", json={"refresh_token": s["refresh_token"]})
    assert r.status_code == 200
    assert _yo(s["access_token"]).status_code == 401  # el access deja de valer en el acto
    assert _renovar(s["refresh_token"]).status_code == 401
    assert Cliente(app).post(f"{M}/logout", json={"refresh_token": s["refresh_token"]}).status_code == 200
    assert Cliente(app).post(f"{M}/logout", json={"refresh_token": "z" * 43}).status_code == 200


def test_un_admin_revoca_el_celular_de_un_usuario(como):
    s = _sesion()
    admin = como(RolEnum.ADMIN, "jefe")
    usuario_id = s["usuario"]["id"]
    lista = admin.get(f"{API}/usuarios/{usuario_id}/dispositivos").json()
    assert [(d["nombre"], d["plataforma"], d["revocado_en"]) for d in lista] == [("Moto G del reparto", "android", None)]
    assert admin.delete(f"{API}/usuarios/{usuario_id}/dispositivos/{s['dispositivo_id']}").status_code == 200
    assert _yo(s["access_token"]).status_code == 401 and _renovar(s["refresh_token"]).status_code == 401
    assert admin.get(f"{API}/usuarios/{usuario_id}/dispositivos").json()[0]["revocado_en"] is not None
    assert admin.delete(f"{API}/usuarios/{usuario_id}/dispositivos/9999").status_code == 404


def test_cada_persona_ve_y_cierra_sus_propios_dispositivos():
    crear_usuario("repa", RolEnum.REPARTIDOR)
    crear_usuario("otro", RolEnum.REPARTIDOR)
    a = _entrar("repa").json()
    b = _entrar("otro", cel={"nombre": "iPhone", "plataforma": "ios"}).json()
    c = Cliente(app)
    mios = c.get(f"{API}/auth/dispositivos", headers=_auth(a["access_token"])).json()
    assert [d["id"] for d in mios] == [a["dispositivo_id"]]
    # No puede cerrar el de otra persona
    r = c.delete(f"{API}/auth/dispositivos/{b['dispositivo_id']}", headers=_auth(a["access_token"]))
    assert r.status_code == 404 and _yo(b["access_token"]).status_code == 200
    assert c.delete(f"{API}/auth/dispositivos/{a['dispositivo_id']}", headers=_auth(a["access_token"])).status_code == 200
    assert _yo(a["access_token"]).status_code == 401


def test_un_token_de_otro_usuario_no_puede_apropiarse_de_un_dispositivo():
    from app.core.security import create_access_token

    a = _sesion()
    crear_usuario("otro", RolEnum.REPARTIDOR)
    with SessionLocal() as db:
        otro = db.scalar(select(Usuario).where(Usuario.username == "otro"))
        falso = create_access_token(user_id=otro.id, token_version=0, audience="movil", dispositivo_id=a["dispositivo_id"])
    assert _yo(falso).status_code == 401  # el dispositivo es de otra persona


def test_cerrar_todas_las_sesiones_invalida_los_access_de_la_app():
    s = _sesion()
    assert _yo(s["access_token"]).status_code == 200
    assert Cliente(app).post(f"{API}/auth/cerrar-sesiones", headers=_auth(s["access_token"])).status_code == 200
    assert _yo(s["access_token"]).status_code == 401  # token_version
    # Y el refresh tampoco sobrevive: un token robado no puede volver a emitir sesiones
    assert _renovar(s["refresh_token"]).status_code == 401


def test_cambiar_la_contrasena_o_desactivar_al_usuario_revoca_los_dispositivos(como):
    s = _sesion()
    assert Cliente(app).post(f"{API}/auth/cambiar-password", headers=_auth(s["access_token"]), json={
        "password_actual": PASSWORD, "password_nueva": "otra-clave-segura-1"}).status_code == 200
    assert _renovar(s["refresh_token"]).status_code == 401
    assert _entrar(password="otra-clave-segura-1").status_code == 200

    admin = como(RolEnum.ADMIN, "jefe")
    s2 = _entrar(password="otra-clave-segura-1").json()
    assert admin.patch(f"{API}/usuarios/{s2['usuario']['id']}", json={"activo": False}).status_code == 200
    assert _renovar(s2["refresh_token"]).status_code == 401


def test_el_bearer_de_la_app_no_necesita_csrf_ni_origen():
    s = _sesion(RolEnum.VENDEDORA, "caja")
    r = Cliente(app).post(f"{API}/turnos", json={"efectivo_inicial": 10},
                          headers={**_auth(s["access_token"]), "Origin": "https://otro-sitio.com"})
    assert r.status_code == 201  # no hay cookies ambientes: no hay nada que falsificar


# ---------- Google en la app ----------


def _google_movil(*, aud, nonce="nonce-del-celular-123", enviado="nonce-del-celular-123", **token):
    return Cliente(app).post(f"{M}/google", json={
        "id_token": id_token(nonce=nonce, aud=aud, **token), "nonce": enviado, "dispositivo": CEL})


def test_google_en_la_app_valida_firma_audiencia_nonce_y_vinculacion(google_activo):
    crear_usuario("repa", RolEnum.REPARTIDOR)
    with SessionLocal() as db:
        db.scalar(select(Usuario)).email = "repa@gmail.com"
        db.commit()
    ok = _google_movil(aud=CLIENT_ANDROID, email="repa@gmail.com")
    assert ok.status_code == 200, ok.text
    claims = decode_access_token(ok.json()["access_token"])
    assert claims["aud"] == "movil" and claims["amr"] == "google"
    assert _google_movil(aud=CLIENT_IOS, sub="g-1", email="repa@gmail.com").status_code == 200  # por sub
    codigos = {
        # el cliente web no es una audiencia de la app
        "web": _google_movil(aud=CLIENT_ID, email="repa@gmail.com"),
        "nonce": _google_movil(aud=CLIENT_ANDROID, enviado="otro-nonce-distinto", email="repa@gmail.com"),
        "no vinculada": _google_movil(aud=CLIENT_ANDROID, sub="g-9", email="extrano@gmail.com"),
        "sin verificar": _google_movil(aud=CLIENT_ANDROID, sub="g-8", email="repa@gmail.com", verificado=False),
    }
    assert {k: (r.status_code, r.json()["error"]["code"]) for k, r in codigos.items()} == {
        "web": (401, "google_token_invalido"),
        "nonce": (401, "google_token_invalido"),
        "no vinculada": (401, "google_no_vinculado"),
        "sin verificar": (401, "google_correo_no_verificado"),
    }


def test_google_en_la_app_sin_configurar():
    r = _google_movil(aud=CLIENT_ANDROID)
    assert r.status_code == 401 and r.json()["error"]["code"] == "google_no_configurado"


def test_la_reautenticacion_con_google_en_la_app(google_activo):
    crear_usuario("jefe", RolEnum.ADMIN)
    with SessionLocal() as db:
        db.scalar(select(Usuario)).email = "jefe@gmail.com"
        db.commit()
    s = _entrar("jefe").json()
    nonce = "nonce-de-la-reautenticacion"
    r = Cliente(app).post(f"{M}/reautenticacion", headers=_auth(s["access_token"]), json={
        "id_token": id_token(nonce=nonce, aud=CLIENT_ANDROID, email="jefe@gmail.com", sub="g-jefe"), "nonce": nonce})
    assert r.status_code == 200 and decode_access_token(r.json()["access_token"])["amr"] == "google"
    ajeno = Cliente(app).post(f"{M}/reautenticacion", headers=_auth(s["access_token"]), json={
        "id_token": id_token(nonce=nonce, aud=CLIENT_ANDROID, email="otro@gmail.com", sub="g-otro"), "nonce": nonce})
    assert ajeno.status_code == 401


def test_los_endpoints_de_la_web_siguen_sin_aceptar_un_refresh_como_bearer():
    s = _sesion()
    assert _yo(s["refresh_token"]).status_code == 401  # un token opaco no es un JWT
