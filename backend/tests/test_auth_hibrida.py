"""Autenticación híbrida (docs/rfc-001 §2): claims, reautenticación, PIN en terminales registrados,
login con Google (OpenID Connect + PKCE) y verificación de Origin.

Google se simula con un par de claves RSA propio: el servidor valida la firma como lo haría con el JWKS
de Google, pero sin salir a Internet.
"""

import hashlib
import time
from base64 import urlsafe_b64encode
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from sqlalchemy import select

from app.core import config
from app.core.security import (
    AMR_GOOGLE,
    AMR_PASSWORD,
    AMR_PIN,
    create_access_token,
    decode_access_token,
    hash_pin,
    verify_pin,
)
from app.db.session import SessionLocal
from app.main import app
from app.models import IdentidadExterna, RolEnum, Terminal, Usuario
from app.services import google
from tests.conftest import PASSWORD, Cliente, crear_usuario, login
from tests.google_falso import CLIENT_ID, OTRA_CLAVE, id_token

API = "/api/v1"
ORIGEN = {"Origin": "http://testserver"}


# ---------- Ayudas ----------


def _usuario(username, rol, **columnas) -> Usuario:
    with SessionLocal() as s:
        u = Usuario(username=username, rol=rol, hashed_password=hash_pin("0") if False else _hash(), **columnas)
        s.add(u)
        s.commit()
        return u


def _hash() -> str:
    from app.core.security import hash_password

    return hash_password(PASSWORD)


def _sesion(usuario: Usuario, *, amr=AMR_PASSWORD, antiguedad_min=0, trm=None, aud="web", minutos=None):
    """Cliente HTTP con una sesión armada a mano (cookie + CSRF), sin pasar por el login."""
    ahora = datetime.now(UTC)
    token = create_access_token(
        user_id=usuario.id, token_version=usuario.token_version, amr=amr,
        auth_time=ahora - timedelta(minutes=antiguedad_min), terminal_id=trm, audience=aud, minutos=minutos,
    )
    c = Cliente(app)
    s = config.get_settings()
    # Mismo dominio que le asigna el cliente a las cookies que recibe del servidor ("testserver" no tiene
    # punto: cookielib lo trata como "testserver.local"); si no, la renovación de la sesión las duplicaría
    c.cookies.set(s.cookie_name, token, domain="testserver.local")
    c.cookies.set(s.csrf_cookie_name, "csrf-de-prueba", domain="testserver.local")
    return c


def _con_pin(username, rol, pin="2580", **columnas) -> Usuario:
    return _usuario(username, rol, pin_hash=hash_pin(pin), **columnas)


def _kiosko(secreto: str) -> Cliente:
    """Equipo registrado, todavía sin sesión: solo tiene la cookie del terminal."""
    c = Cliente(app)
    c.cookies.set(config.get_settings().terminal_cookie_name, secreto)
    return c


def _registrar_terminal(admin_client, tipo="Caja", nombre="Caja 1") -> str:
    r = admin_client.post(f"{API}/auth/terminales", json={"nombre": nombre, "tipo": tipo})
    assert r.status_code == 201, r.text
    return admin_client.cookies.get(config.get_settings().terminal_cookie_name)


def _pin(c, usuario_id, pin, headers=ORIGEN):
    return c.post(f"{API}/auth/pin", json={"usuario_id": usuario_id, "pin": pin}, headers=headers)


def _claims(c) -> dict:
    return decode_access_token(c.cookies.get(config.get_settings().cookie_name))


# ---------- Claims y reautenticación ----------


def test_el_login_emite_amr_auth_time_y_audiencia(como):
    como(RolEnum.ADMIN, "jefe")
    c = login("jefe")
    claims = _claims(c)
    assert (claims["amr"], claims["aud"]) == (AMR_PASSWORD, "web")
    assert abs(claims["auth_time"] - time.time()) < 10
    me = c.get(f"{API}/auth/me").json()
    assert me["sesion"]["metodo"] == "pwd" and me["sesion"]["fuerte"] is True


def test_un_token_anterior_a_la_autenticacion_hibrida_sigue_valiendo():
    """Sin amr, auth_time ni aud (emitido antes de la Fase 4): se lee como sesión web con contraseña."""
    u = crear_usuario("vieja", RolEnum.VENDEDORA)
    viejo = jwt.encode({"sub": str(u.id), "ver": 0, "iat": int(time.time()), "exp": int(time.time()) + 600},
                       config.get_settings().jwt_secret, algorithm="HS256")
    c = Cliente(app)
    c.cookies.set(config.get_settings().cookie_name, viejo)
    assert c.get(f"{API}/auth/me").status_code == 200


def test_la_gestion_sensible_pide_reautenticacion_si_la_sesion_es_vieja(como):
    admin = crear_usuario("jefe", RolEnum.ADMIN)
    c = _sesion(admin, antiguedad_min=40)
    nuevo = {"username": "nuevo", "rol": "Vendedora", "password": "clave-segura-123"}
    r = c.post(f"{API}/usuarios", json=nuevo)
    assert r.status_code == 401 and r.json()["error"]["code"] == "reautenticacion_requerida"
    assert c.get(f"{API}/auth/me").json()["sesion"]["fuerte"] is False  # lo mismo que ve la pantalla

    mala = c.post(f"{API}/auth/reautenticacion", json={"password": "incorrecta-123"})
    assert mala.status_code == 401 and mala.json()["error"]["code"] == "invalid_credentials"
    ok = c.post(f"{API}/auth/reautenticacion", json={"password": PASSWORD})
    assert ok.status_code == 200 and ok.json()["sesion"]["fuerte"] is True
    assert c.post(f"{API}/usuarios", json=nuevo).status_code == 201  # sin perder lo que se estaba haciendo
    assert _claims(c)["amr"] == AMR_PASSWORD


GESTION_SENSIBLE = [
    ("post", "/productos", {"nombre": "Nuevo", "precio_venta": 10}),
    ("patch", "/productos/1", {"precio_venta": 99}),
    ("put", "/productos/1/stock", {"stock_mostrador": 3}),
    ("post", "/contabilidad/puntos-entrega/1/descuentos", {"porcentaje": 10, "motivo": "x"}),
    ("patch", "/contabilidad/puntos-entrega/1/descuentos/1", {"porcentaje": 5}),
    ("post", "/contabilidad/clientes/1/notas-credito", {"monto": 10, "observacion": "x"}),
    ("post", "/contabilidad/clientes/1/ajustes", {"importe": 10, "observacion": "x"}),
    ("post", "/turnos/1/cierre", {"monto_declarado": 0}),
    ("post", "/auth/terminales", {"nombre": "Otra", "tipo": "Caja"}),
    ("patch", "/auth/terminales/1", {"activo": False}),
]


@pytest.mark.parametrize("metodo,ruta,body", GESTION_SENSIBLE)
def test_una_sesion_con_pin_no_habilita_la_gestion_sensible(metodo, ruta, body):
    enc = _con_pin("encargada", RolEnum.ENCARGADA)
    c = _sesion(enc, amr=AMR_PIN)
    r = getattr(c, metodo)(API + ruta, json=body)
    assert r.status_code == 401 and r.json()["error"]["code"] == "reautenticacion_requerida", r.text


def test_cambiar_un_precio_exige_autenticacion_fuerte_pero_renombrar_no(catalogo):
    enc = _con_pin("encargada", RolEnum.ENCARGADA)
    c = _sesion(enc, amr=AMR_PIN)
    pan = catalogo["pan"]
    assert c.patch(f"{API}/productos/{pan}", json={"nombre": "Pan francés"}).status_code == 200
    r = c.patch(f"{API}/productos/{pan}", json={"precio_venta": 120})
    assert r.status_code == 401 and r.json()["error"]["code"] == "reautenticacion_requerida"
    assert c.post(f"{API}/auth/reautenticacion", json={"password": PASSWORD}).status_code == 200
    assert c.patch(f"{API}/productos/{pan}", json={"precio_venta": 120}).status_code == 200


def test_la_caja_sigue_operando_con_pin_sin_reautenticar(catalogo):
    vend = _con_pin("vendedora", RolEnum.VENDEDORA)
    c = _sesion(vend, amr=AMR_PIN)
    assert c.post(f"{API}/turnos", json={"efectivo_inicial": 100}).status_code == 201
    r = c.post(f"{API}/ventas", json={"items": [{"producto_id": catalogo["pan"], "cantidad": 1}]})
    assert r.status_code == 201


# ---------- Origin ----------


def test_una_escritura_con_cookie_desde_otro_origen_se_rechaza(como):
    como(RolEnum.VENDEDORA, "caja")
    c = login("caja")
    r = c.post(f"{API}/turnos", json={"efectivo_inicial": 1}, headers={"Origin": "https://sitio-malo.com"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "origen_invalido"
    r = c.post(f"{API}/turnos", json={"efectivo_inicial": 1}, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "origen_invalido"
    r = c.post(f"{API}/turnos", json={"efectivo_inicial": 1}, headers={"Origin": "null"})
    assert r.status_code == 403
    # El propio origen, y los clientes que no son navegadores (sin Origin), pasan
    assert c.post(f"{API}/turnos", json={"efectivo_inicial": 1}, headers=ORIGEN).status_code == 201


def test_los_origenes_extra_se_configuran(como, monkeypatch):
    como(RolEnum.VENDEDORA, "caja")
    c = login("caja")
    monkeypatch.setenv("ORIGENES_PERMITIDOS", "https://app.ejemplo.com, otro.com")
    config.get_settings.cache_clear()
    try:
        r = c.post(f"{API}/turnos", json={"efectivo_inicial": 1}, headers={"Origin": "https://app.ejemplo.com"})
        assert r.status_code == 201
    finally:
        monkeypatch.undo()
        config.get_settings.cache_clear()


def test_las_cookies_solo_valen_con_audiencia_web_y_el_bearer_acepta_la_movil():
    u = crear_usuario("movil", RolEnum.VENDEDORA)
    movil = create_access_token(user_id=u.id, token_version=0, audience="movil")
    c = Cliente(app)
    c.cookies.set(config.get_settings().cookie_name, movil)
    assert c.get(f"{API}/auth/me").status_code == 401  # un token de la app no sirve como cookie
    assert Cliente(app).get(f"{API}/auth/me", headers={"Authorization": f"Bearer {movil}"}).status_code == 200
    web = create_access_token(user_id=u.id, token_version=0)
    assert Cliente(app).get(f"{API}/auth/me", headers={"Authorization": f"Bearer {web}"}).status_code == 200


# ---------- Terminales y PIN ----------


def test_el_pin_sin_terminal_registrado_es_403():
    vend = _con_pin("vendedora", RolEnum.VENDEDORA)
    r = _pin(Cliente(app), vend.id, "2580")
    assert r.status_code == 403 and r.json()["error"]["code"] == "terminal_no_registrada"
    r = _pin(_kiosko("secreto-que-no-existe"), vend.id, "2580")
    assert r.status_code == 403 and r.json()["error"]["code"] == "terminal_no_registrada"


def test_registrar_un_terminal_guarda_solo_el_hash_y_pone_la_cookie_del_equipo(como):
    como(RolEnum.ENCARGADA, "enc")
    c = login("enc")
    r = c.post(f"{API}/auth/terminales", json={"nombre": "Caja del mostrador", "tipo": "Caja"})
    assert r.status_code == 201, r.text
    cookie = next(x for x in r.headers.get_list("set-cookie") if x.startswith("panaderia_terminal="))
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Max-Age=" in cookie
    secreto = c.cookies.get("panaderia_terminal")
    assert len(secreto) >= 40  # 256 bits
    with SessionLocal() as s:
        t = s.scalar(select(Terminal))
        assert t.secreto_hash == hashlib.sha256(secreto.encode()).hexdigest()
        assert secreto not in (t.secreto_hash, t.nombre)
    assert [x["nombre"] for x in c.get(f"{API}/auth/terminales").json()] == ["Caja del mostrador"]


def test_login_con_pin_en_un_equipo_registrado(como):
    como(RolEnum.ADMIN, "jefe")
    admin = login("jefe")
    kiosko = _kiosko(_registrar_terminal(admin))
    vend = _con_pin("vendedora", RolEnum.VENDEDORA, nombre="Pamela")

    r = _pin(kiosko, vend.id, "2580")
    assert r.status_code == 200, r.text
    assert r.json()["username"] == "vendedora"
    claims = _claims(kiosko)
    assert claims["amr"] == AMR_PIN and claims["trm"] is not None and claims["aud"] == "web"
    assert claims["exp"] - claims["iat"] <= 600 * 60  # hasta 10 h
    me = kiosko.get(f"{API}/auth/me").json()
    assert me["sesion"]["metodo"] == "pin" and me["sesion"]["fuerte"] is False
    cookies = " ".join(r.headers.get_list("set-cookie"))
    assert "SameSite=strict" in cookies and "panaderia_csrf=" in cookies
    # La sesión opera como cualquier otra: abre turno con CSRF
    assert kiosko.post(f"{API}/turnos", json={"efectivo_inicial": 10}).status_code == 201


def test_el_login_con_pin_exige_el_origen_propio(como):
    como(RolEnum.ADMIN, "jefe")
    kiosko = _kiosko(_registrar_terminal(login("jefe")))
    vend = _con_pin("vendedora", RolEnum.VENDEDORA)
    for cabeceras in ({}, {"Origin": "https://sitio-malo.com"}, {"Sec-Fetch-Site": "cross-site"}):
        r = _pin(kiosko, vend.id, "2580", headers=cabeceras)
        assert r.status_code == 403 and r.json()["error"]["code"] == "origen_invalido", cabeceras
    assert _pin(kiosko, vend.id, "2580", headers={"Sec-Fetch-Site": "same-origin"}).status_code == 200


def test_cinco_pin_incorrectos_bloquean_el_pin_hasta_que_se_libere(como):
    como(RolEnum.ADMIN, "jefe")
    admin = login("jefe")
    kiosko = _kiosko(_registrar_terminal(admin))
    vend = _con_pin("vendedora", RolEnum.VENDEDORA)

    for _ in range(4):
        r = _pin(kiosko, vend.id, "1357")
        assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_credentials"
    assert _pin(kiosko, vend.id, "1357").status_code == 401  # el quinto fallo bloquea
    bloqueado = _pin(kiosko, vend.id, "2580")  # ni el PIN correcto entra
    assert bloqueado.status_code == 401 and bloqueado.json()["error"]["code"] == "pin_bloqueado"
    with SessionLocal() as s:
        assert s.get(Usuario, vend.id).pin_bloqueado is True

    # Un admin lo desbloquea (contraseña o Google también lo hacen al ingresar)
    assert admin.post(f"{API}/usuarios/{vend.id}/pin/desbloqueo").status_code == 200
    assert _pin(kiosko, vend.id, "2580").status_code == 200


def test_ingresar_con_contrasena_o_google_libera_el_pin_bloqueado(como):
    como(RolEnum.ADMIN, "jefe")
    kiosko = _kiosko(_registrar_terminal(login("jefe")))
    vend = _con_pin("vendedora", RolEnum.VENDEDORA, pin_fallidos=5, pin_bloqueado=True)
    assert _pin(kiosko, vend.id, "2580").status_code == 401
    assert login("vendedora") is not None  # contraseña
    assert _pin(kiosko, vend.id, "2580").status_code == 200


def test_los_fallos_se_cuentan_en_la_base_y_un_acierto_los_reinicia(como):
    como(RolEnum.ADMIN, "jefe")
    kiosko = _kiosko(_registrar_terminal(login("jefe")))
    vend = _con_pin("vendedora", RolEnum.VENDEDORA)
    for _ in range(3):
        _pin(kiosko, vend.id, "1357")
    with SessionLocal() as s:
        assert s.get(Usuario, vend.id).pin_fallidos == 3
    assert _pin(kiosko, vend.id, "2580").status_code == 200
    with SessionLocal() as s:
        assert s.get(Usuario, vend.id).pin_fallidos == 0


def test_el_pin_respeta_el_tipo_de_equipo_y_el_rol(como):
    como(RolEnum.ADMIN, "jefe")
    admin = login("jefe")
    caja = _kiosko(_registrar_terminal(admin, "Caja", "Caja 1"))
    cuadra = _kiosko(_registrar_terminal(admin, "Cuadra", "Tablet"))
    vend = _con_pin("vendedora", RolEnum.VENDEDORA)
    pan = _con_pin("panadero", RolEnum.PANADERO)
    enc = _con_pin("encargada", RolEnum.ENCARGADA)
    jefe = _con_pin("otro_admin", RolEnum.ADMIN)  # un admin no usa PIN aunque tenga un hash cargado
    assert _pin(caja, vend.id, "2580").status_code == 200
    assert _pin(Cliente_con(caja), enc.id, "2580").status_code == 200
    assert _pin(Cliente_con(caja), pan.id, "2580").status_code == 401  # el panadero entra por la tablet
    assert _pin(cuadra, pan.id, "2580").status_code == 200
    assert _pin(Cliente_con(cuadra), vend.id, "2580").status_code == 401
    assert _pin(Cliente_con(caja), jefe.id, "2580").status_code == 401
    inexistente = _pin(Cliente_con(caja), 9999, "2580")
    assert inexistente.status_code == 401 and inexistente.json()["error"]["code"] == "invalid_credentials"


def Cliente_con(kiosko: Cliente) -> Cliente:  # noqa: N802  (un equipo nuevo con el mismo terminal)
    return _kiosko(kiosko.cookies.get(config.get_settings().terminal_cookie_name))


def test_la_pantalla_de_ingreso_lista_a_quienes_pueden_usar_pin(como):
    como(RolEnum.ADMIN, "jefe")
    admin = login("jefe")
    sin_equipo = Cliente(app).get(f"{API}/auth/metodos").json()
    assert sin_equipo == {"password": True, "google": False, "terminal": None}

    kiosko = _kiosko(_registrar_terminal(admin))
    _con_pin("vendedora", RolEnum.VENDEDORA, nombre="Pamela")
    _con_pin("enc", RolEnum.ENCARGADA, nombre="Ana")
    _con_pin("panadero", RolEnum.PANADERO)  # no entra por la caja
    _usuario("sin_pin", RolEnum.VENDEDORA)
    _con_pin("baja", RolEnum.VENDEDORA, activo=False)
    m = kiosko.get(f"{API}/auth/metodos").json()
    assert m["terminal"]["tipo"] == "Caja"
    assert [u["username"] for u in m["terminal"]["usuarios"]] == ["enc", "vendedora"]
    assert "pin_hash" not in str(m)


def test_desactivar_un_terminal_invalida_sus_sesiones_pin(como):
    como(RolEnum.ADMIN, "jefe")
    admin = login("jefe")
    kiosko = _kiosko(_registrar_terminal(admin))
    vend = _con_pin("vendedora", RolEnum.VENDEDORA)
    assert _pin(kiosko, vend.id, "2580").status_code == 200
    assert kiosko.get(f"{API}/auth/me").status_code == 200

    terminal_id = admin.get(f"{API}/auth/terminales").json()[0]["id"]
    assert admin.patch(f"{API}/auth/terminales/{terminal_id}", json={"activo": False}).status_code == 200
    assert kiosko.get(f"{API}/auth/me").status_code == 401  # la sesión ya emitida deja de valer
    assert _pin(Cliente_con(kiosko), vend.id, "2580").status_code == 403  # y no entran más PIN


def test_cerrar_el_turno_cierra_la_sesion_con_pin(como):
    como(RolEnum.ADMIN, "jefe")
    kiosko = _kiosko(_registrar_terminal(login("jefe")))
    vend = _con_pin("vendedora", RolEnum.VENDEDORA)
    _pin(kiosko, vend.id, "2580")
    kiosko.post(f"{API}/turnos", json={"efectivo_inicial": 10})
    r = kiosko.post(f"{API}/turnos/actual/cierre", json={"monto_declarado": 10})
    assert r.status_code == 200
    borradas = r.headers.get_list("set-cookie")
    assert any(c.startswith("panaderia_session=") and "Max-Age=0" in c for c in borradas)
    assert kiosko.get(f"{API}/auth/me").status_code == 401
    # Con contraseña, en cambio, el cierre no cierra la sesión
    c = login("vendedora")
    c.post(f"{API}/turnos", json={"efectivo_inicial": 10})
    assert not any(x.startswith("panaderia_session=")
                   for x in c.post(f"{API}/turnos/actual/cierre", json={"monto_declarado": 10})
                   .headers.get_list("set-cookie"))


def test_cambiar_o_quitar_el_pin_cierra_las_sesiones_abiertas(como):
    como(RolEnum.ADMIN, "jefe")
    admin = login("jefe")
    kiosko = _kiosko(_registrar_terminal(admin))
    vend = _con_pin("vendedora", RolEnum.VENDEDORA)
    _pin(kiosko, vend.id, "2580")
    assert admin.put(f"{API}/usuarios/{vend.id}/pin", json={"pin": "9264"}).status_code == 200
    assert kiosko.get(f"{API}/auth/me").status_code == 401
    assert _pin(Cliente_con(kiosko), vend.id, "2580").status_code == 401
    assert _pin(Cliente_con(kiosko), vend.id, "9264").status_code == 200
    assert admin.delete(f"{API}/usuarios/{vend.id}/pin").json()["tiene_pin"] is False
    assert _pin(Cliente_con(kiosko), vend.id, "9264").status_code == 401


def test_validaciones_del_pin(como):
    como(RolEnum.ADMIN, "jefe")
    admin = login("jefe")
    vend = _usuario("vendedora", RolEnum.VENDEDORA)
    rep = _usuario("reparto", RolEnum.REPARTIDOR)
    for malo in ("123", "1234567", "12a4", "", "    "):
        assert admin.put(f"{API}/usuarios/{vend.id}/pin", json={"pin": malo}).status_code == 422, malo
    for debil in ("1111", "1234", "4321", "0000", "345678"):
        r = admin.put(f"{API}/usuarios/{vend.id}/pin", json={"pin": debil})
        assert r.status_code == 422 and r.json()["error"]["code"] == "pin_debil", debil
    r = admin.put(f"{API}/usuarios/{rep.id}/pin", json={"pin": "2580"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "rol_sin_pin"
    ok = admin.put(f"{API}/usuarios/{vend.id}/pin", json={"pin": "2580"})
    assert ok.status_code == 200 and ok.json()["tiene_pin"] is True and "pin_hash" not in ok.text
    assert admin.put(f"{API}/usuarios/9999/pin", json={"pin": "2580"}).status_code == 404


def test_el_pin_se_guarda_con_bcrypt_sobre_un_hmac_con_pepper(monkeypatch):
    monkeypatch.setenv("PIN_PEPPER", "pepper-uno-" + "x" * 30)
    config.get_settings.cache_clear()
    try:
        h = hash_pin("2580")
        assert h.startswith("$2") and "2580" not in h
        assert verify_pin("2580", h) and not verify_pin("2581", h)
        monkeypatch.setenv("PIN_PEPPER", "pepper-dos-" + "x" * 30)
        config.get_settings.cache_clear()
        # Con otro pepper (p. ej. una base robada sin el secreto del servidor) el PIN correcto no verifica
        assert not verify_pin("2580", h)
    finally:
        monkeypatch.undo()
        config.get_settings.cache_clear()


def test_los_intentos_de_pin_desde_una_ip_se_limitan(como):
    como(RolEnum.ADMIN, "jefe")
    kiosko = _kiosko(_registrar_terminal(login("jefe")))
    vendedoras = [_con_pin(f"v{i}", RolEnum.VENDEDORA) for i in range(4)]
    # Cada persona se bloquea a los 5 fallos; probar PIN en varias personas desde el mismo equipo tampoco
    # sirve: a los 15 intentos (3 × el límite por persona) el equipo se frena
    codigos = [_pin(kiosko, u.id, "1357").status_code for u in vendedoras[:3] for _ in range(5)]
    assert codigos == [401] * 15
    r = _pin(kiosko, vendedoras[3].id, "1357")
    assert r.status_code == 429 and r.json()["error"]["code"] == "too_many_requests"



def test_la_administracion_de_pin_y_usuarios_es_solo_de_admin(como):
    enc = como(RolEnum.ENCARGADA)
    vend = _usuario("v", RolEnum.VENDEDORA)
    assert enc.put(f"{API}/usuarios/{vend.id}/pin", json={"pin": "2580"}).status_code == 403
    assert enc.get(f"{API}/usuarios").status_code == 403


# ---------- Correo y vinculación de usuarios ----------


def test_el_correo_es_unico_y_se_guarda_en_minusculas(como):
    como(RolEnum.ADMIN, "jefe")
    admin = login("jefe")
    r = admin.post(f"{API}/usuarios", json={"username": "ana", "rol": "Vendedora", "password": "clave-segura-123",
                                            "email": "Ana.Perez@Gmail.com"})
    assert r.status_code == 201 and r.json()["email"] == "ana.perez@gmail.com"
    dup = admin.post(f"{API}/usuarios", json={"username": "beto", "rol": "Vendedora", "password": "clave-segura-123",
                                              "email": "ANA.perez@gmail.com"})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "email_en_uso"
    assert admin.post(f"{API}/usuarios", json={"username": "c", "rol": "Vendedora", "password": "clave-segura-123",
                                               "email": "no-es-un-correo"}).status_code == 422
    beto = admin.post(f"{API}/usuarios", json={"username": "beto", "rol": "Vendedora",
                                               "password": "clave-segura-123"}).json()
    assert admin.patch(f"{API}/usuarios/{beto['id']}", json={"email": "ana.perez@gmail.com"}).status_code == 409
    assert admin.patch(f"{API}/usuarios/{beto['id']}", json={"email": "beto@gmail.com"}).json()["email"] == "beto@gmail.com"
    assert admin.patch(f"{API}/usuarios/{beto['id']}", json={"email": None}).json()["email"] is None


def test_un_cambio_de_rol_a_uno_sin_pin_quita_el_pin(como):
    como(RolEnum.ADMIN, "jefe")
    admin = login("jefe")
    vend = _con_pin("vendedora", RolEnum.VENDEDORA)
    r = admin.patch(f"{API}/usuarios/{vend.id}", json={"rol": "Repartidor"})
    assert r.status_code == 200 and r.json()["tiene_pin"] is False


# ---------- Google ----------


def _id_token(**kw):
    return id_token(**kw)


def _iniciar(c, **params):
    r = c.get(f"{API}/auth/google/inicio", params=params, follow_redirects=False)
    assert r.status_code == 302, r.text
    destino = urlsplit(r.headers["location"])
    return r, {k: v[0] for k, v in parse_qs(destino.query).items()}, destino


def _volver_de_google(c, monkeypatch, q, *, state=None, **token):
    """Simula la vuelta: Google devuelve un código y el servidor lo canjea (acá, por un id_token firmado)."""
    visto = {}

    def canje(code, verifier):
        visto["verifier"] = verifier
        # PKCE: lo que se envió a Google (challenge) es el SHA-256 del verifier que usa el servidor
        assert q["code_challenge"] == urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        return _id_token(nonce=q["nonce"], **token)

    monkeypatch.setattr(google, "intercambiar_codigo", canje)
    r = c.get(f"{API}/auth/google/callback", params={"code": "codigo-de-google", "state": state or q["state"]},
              follow_redirects=False)
    return r, visto


def test_el_inicio_con_google_arma_la_solicitud_con_pkce_y_la_cookie_del_flujo(google_activo):
    c = Cliente(app)
    r, q, destino = _iniciar(c)
    assert destino.netloc == "accounts.google.com"
    assert q["client_id"] == CLIENT_ID and q["response_type"] == "code" and q["scope"] == "openid email profile"
    assert q["redirect_uri"] == "http://testserver/api/v1/auth/google/callback"
    assert q["code_challenge_method"] == "S256" and len(q["state"]) >= 30 and len(q["nonce"]) >= 30
    cookie = next(x for x in r.headers.get_list("set-cookie") if x.startswith("panaderia_oauth="))
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Max-Age=600" in cookie
    # La cookie del flujo no sirve como sesión
    sesion = Cliente(app)
    sesion.cookies.set(config.get_settings().cookie_name, c.cookies.get("panaderia_oauth"))
    assert sesion.get(f"{API}/auth/me").status_code == 401
    assert q["prompt"] == "select_account"


def test_login_con_google_vincula_por_correo_y_deja_una_sesion_strict_con_csrf(google_activo):
    _usuario("ana", RolEnum.VENDEDORA, email="ana@gmail.com")
    c = Cliente(app)
    _, q, _ = _iniciar(c)
    r, _ = _volver_de_google(c, google_activo, q)
    assert r.status_code == 303 and r.headers["location"] == "/"
    cookies = r.headers.get_list("set-cookie")
    sesion = next(x for x in cookies if x.startswith("panaderia_session="))
    assert "SameSite=strict" in sesion and "HttpOnly" in sesion  # la sesión sigue siendo Strict
    assert any(x.startswith("panaderia_csrf=") for x in cookies)  # con un CSRF nuevo
    assert any(x.startswith("panaderia_oauth=") and "Max-Age=0" in x for x in cookies)  # y se usa una sola vez
    assert _claims(c)["amr"] == AMR_GOOGLE
    assert c.get(f"{API}/auth/me").json()["sesion"] == {
        **c.get(f"{API}/auth/me").json()["sesion"], "metodo": "google", "fuerte": True}

    # Las escrituras siguen exigiendo CSRF
    r = c.post(f"{API}/turnos", json={"efectivo_inicial": 5}, headers={"X-CSRF-Token": "falso"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_failed"
    assert c.post(f"{API}/turnos", json={"efectivo_inicial": 5}).status_code == 201
    with SessionLocal() as s:
        i = s.scalar(select(IdentidadExterna))
        assert (i.sub, i.email) == ("g-1", "ana@gmail.com") and i.ultimo_uso is not None


def test_despues_de_vincular_se_entra_por_sub_aunque_cambie_el_correo(google_activo):
    _usuario("ana", RolEnum.VENDEDORA, email="ana@gmail.com")
    c = Cliente(app)
    _, q, _ = _iniciar(c)
    assert _volver_de_google(c, google_activo, q)[0].headers["location"] == "/"

    # Ana cambió el correo en Google: el sub es el mismo y entra igual
    c2 = Cliente(app)
    _, q2, _ = _iniciar(c2)
    r, _ = _volver_de_google(c2, google_activo, q2, email="ana.nueva@gmail.com")
    assert r.status_code == 303 and r.headers["location"] == "/"
    with SessionLocal() as s:
        assert s.scalar(select(IdentidadExterna.email)) == "ana.nueva@gmail.com"


def test_una_cuenta_de_google_no_vinculada_no_entra(google_activo):
    _usuario("ana", RolEnum.VENDEDORA, email="ana@gmail.com")
    c = Cliente(app)
    _, q, _ = _iniciar(c)
    r, _ = _volver_de_google(c, google_activo, q, sub="g-999", email="extrano@gmail.com")
    assert r.status_code == 303 and r.headers["location"] == "/login?error=google_no_vinculado"
    assert not any(x.startswith("panaderia_session=") and "Max-Age=0" not in x for x in r.headers.get_list("set-cookie"))
    assert c.get(f"{API}/auth/me").status_code == 401
    with SessionLocal() as s:
        assert s.scalar(select(IdentidadExterna)) is None  # no hay alta automática


def test_un_usuario_inactivo_o_con_otra_cuenta_vinculada_no_entra(google_activo):
    _usuario("baja", RolEnum.VENDEDORA, email="baja@gmail.com", activo=False)
    c = Cliente(app)
    _, q, _ = _iniciar(c)
    assert _volver_de_google(c, google_activo, q, sub="g-2", email="baja@gmail.com")[0].headers["location"] \
        == "/login?error=google_no_vinculado"

    _usuario("ana", RolEnum.VENDEDORA, email="ana@gmail.com")
    c1 = Cliente(app)
    _, q1, _ = _iniciar(c1)
    assert _volver_de_google(c1, google_activo, q1)[0].headers["location"] == "/"
    c2 = Cliente(app)
    _, q2, _ = _iniciar(c2)
    # Otra cuenta de Google con el mismo correo (p. ej. reasignado): ya hay una vinculada, no se agrega otra
    assert _volver_de_google(c2, google_activo, q2, sub="g-otra")[0].headers["location"] \
        == "/login?error=google_no_vinculado"


def test_un_state_invalido_rechaza_el_callback(google_activo):
    _usuario("ana", RolEnum.VENDEDORA, email="ana@gmail.com")
    c = Cliente(app)
    _, q, _ = _iniciar(c)
    r, visto = _volver_de_google(c, google_activo, q, state="state-de-otro-navegador")
    assert r.headers["location"] == "/login?error=google_estado_invalido" and visto == {}
    assert c.get(f"{API}/auth/me").status_code == 401

    # Sin la cookie del flujo (otro navegador, o ya usada) tampoco: el callback no inicia sesión solo
    otro = Cliente(app)
    r, _ = _volver_de_google(otro, google_activo, q)
    assert r.headers["location"] == "/login?error=google_estado_invalido"
    # La cookie se usa una sola vez: tras un login correcto, repetir la vuelta falla
    c = Cliente(app)
    _, q, _ = _iniciar(c)
    ok, _ = _volver_de_google(c, google_activo, q)
    assert ok.headers["location"] == "/"
    repetido, _ = _volver_de_google(c, google_activo, q)
    assert repetido.headers["location"] == "/login?error=google_estado_invalido"


def test_una_cookie_del_flujo_vencida_o_adulterada_se_rechaza(google_activo):
    c = Cliente(app)
    _, q, _ = _iniciar(c)
    vieja = jwt.encode({"aud": "oauth-panaderia", "st": q["state"], "nc": q["nonce"], "cv": "x" * 50,
                        "exp": int(time.time()) - 5}, google._clave_cookie(), algorithm="HS256")
    c.cookies.set("panaderia_oauth", vieja)
    r, _ = _volver_de_google(c, google_activo, q)
    assert r.headers["location"] == "/login?error=google_estado_invalido"
    falsa = jwt.encode({"aud": "oauth-panaderia", "st": q["state"], "nc": q["nonce"], "cv": "x" * 50,
                        "exp": int(time.time()) + 600}, "otra-clave-de-32-bytes-minimo-aaaaaaa", algorithm="HS256")
    c.cookies.set("panaderia_oauth", falsa)
    assert _volver_de_google(c, google_activo, q)[0].headers["location"] == "/login?error=google_estado_invalido"


@pytest.mark.parametrize("token,error", [
    ({"verificado": False}, "google_correo_no_verificado"),
    ({"aud": "otro-cliente.apps.googleusercontent.com"}, "google_token_invalido"),
    ({"vence_en": -10}, "google_token_invalido"),
    ({"clave": OTRA_CLAVE}, "google_token_invalido"),
    ({"emisor": "https://accounts.evil.com"}, "google_token_invalido"),
])
def test_el_id_token_se_valida_por_completo(google_activo, token, error):
    _usuario("ana", RolEnum.VENDEDORA, email="ana@gmail.com")
    c = Cliente(app)
    _, q, _ = _iniciar(c)
    r, _ = _volver_de_google(c, google_activo, q, **token)
    assert r.headers["location"] == f"/login?error={error}"
    assert c.get(f"{API}/auth/me").status_code == 401


@pytest.mark.parametrize("algoritmo,clave", [("HS256", "secreto-del-atacante-de-32-bytes-o-mas!"), ("none", None)])
def test_el_id_token_solo_acepta_rs256(google_activo, algoritmo, clave):
    """Confusión de algoritmo: un token firmado con HMAC (o sin firma) no puede colarse como si fuera de Google."""
    _usuario("ana", RolEnum.VENDEDORA, email="ana@gmail.com")
    c = Cliente(app)
    _, q, _ = _iniciar(c)
    ahora = int(time.time())
    falso = jwt.encode({"iss": "https://accounts.google.com", "aud": CLIENT_ID, "sub": "g-1", "email": "ana@gmail.com",
                        "email_verified": True, "nonce": q["nonce"], "iat": ahora, "exp": ahora + 600},
                       clave, algorithm=algoritmo)
    google_activo.setattr(google, "intercambiar_codigo", lambda code, verifier: falso)
    r = c.get(f"{API}/auth/google/callback", params={"code": "x", "state": q["state"]}, follow_redirects=False)
    assert r.headers["location"] == "/login?error=google_token_invalido"
    assert c.get(f"{API}/auth/me").status_code == 401


def test_el_nonce_del_token_debe_ser_el_de_la_solicitud(google_activo):
    _usuario("ana", RolEnum.VENDEDORA, email="ana@gmail.com")
    c = Cliente(app)
    _, q, _ = _iniciar(c)
    google_activo.setattr(google, "intercambiar_codigo", lambda code, verifier: _id_token(nonce="de-otra-solicitud"))
    r = c.get(f"{API}/auth/google/callback", params={"code": "x", "state": q["state"]}, follow_redirects=False)
    assert r.headers["location"] == "/login?error=google_token_invalido"


def test_se_puede_restringir_a_un_dominio_de_google_workspace(google_activo):
    google_activo.setenv("GOOGLE_HOSTED_DOMAIN", "panaderia.com")
    config.get_settings.cache_clear()
    _usuario("ana", RolEnum.VENDEDORA, email="ana@panaderia.com")
    c = Cliente(app)
    _, q, destino = _iniciar(c)
    assert q["hd"] == "panaderia.com"
    r, _ = _volver_de_google(c, google_activo, q, email="ana@panaderia.com")  # sin el claim hd
    assert r.headers["location"] == "/login?error=google_dominio_no_permitido"
    c2 = Cliente(app)
    _, q2, _ = _iniciar(c2)
    assert _volver_de_google(c2, google_activo, q2, email="ana@panaderia.com", hd="panaderia.com")[0] \
        .headers["location"] == "/"


def test_si_google_cancela_o_falla_se_vuelve_al_ingreso_con_un_error(google_activo):
    c = Cliente(app)
    _, q, _ = _iniciar(c)
    r = c.get(f"{API}/auth/google/callback", params={"error": "access_denied", "state": q["state"]},
              follow_redirects=False)
    assert r.headers["location"] == "/login?error=google_cancelado"
    c = Cliente(app)
    _, q, _ = _iniciar(c)
    google_activo.setattr(google.httpx, "post", lambda *a, **k: (_ for _ in ()).throw(google.httpx.ConnectError("x")))
    r = c.get(f"{API}/auth/google/callback", params={"code": "x", "state": q["state"]}, follow_redirects=False)
    assert r.headers["location"] == "/login?error=google_error"


def test_el_destino_de_vuelta_no_puede_ser_otro_sitio(google_activo):
    _usuario("ana", RolEnum.VENDEDORA, email="ana@gmail.com")
    for volver, esperado in (("/caja", "/caja"), ("//evil.com", "/"), ("https://evil.com", "/"),
                             ("/\\evil.com", "/"), ("evil", "/")):
        c = Cliente(app)
        _, q, _ = _iniciar(c, volver=volver)
        r, _ = _volver_de_google(c, google_activo, q)
        assert r.headers["location"] == esperado, volver


def test_sin_configurar_google_no_hay_boton_ni_flujo():
    assert Cliente(app).get(f"{API}/auth/metodos").json()["google"] is False
    r = Cliente(app).get(f"{API}/auth/google/inicio", follow_redirects=False)
    assert r.status_code == 401 and r.json()["error"]["code"] == "google_no_configurado"
    assert Cliente(app).get(f"{API}/auth/google/callback", follow_redirects=False).headers["location"] \
        == "/login?error=google_no_configurado"


def test_con_google_configurado_la_pantalla_lo_ofrece(google_activo):
    assert Cliente(app).get(f"{API}/auth/metodos").json()["google"] is True


def test_reautenticar_con_google_renueva_auth_time_solo_para_la_misma_persona(google_activo):
    ana = _usuario("ana", RolEnum.ADMIN, email="ana@gmail.com")
    _usuario("beto", RolEnum.ADMIN, email="beto@gmail.com")
    c = _sesion(ana, antiguedad_min=40)
    assert c.post(f"{API}/usuarios", json={"username": "xx1", "rol": "Vendedora",
                                            "password": "clave-segura-123"}).status_code == 401

    # Con la cuenta de Beto: no es la de la sesión
    r0 = c.get(f"{API}/auth/google/reautenticacion", params={"volver": "/admin/usuarios"}, follow_redirects=False)
    assert r0.status_code == 302 and parse_qs(urlsplit(r0.headers["location"]).query)["prompt"] == ["login"]
    q0 = {k: v[0] for k, v in parse_qs(urlsplit(r0.headers["location"]).query).items()}
    r, _ = _volver_de_google(c, google_activo, q0, sub="g-beto", email="beto@gmail.com")
    assert r.headers["location"] == "/admin/usuarios?reauth_error=google_cuenta_distinta"

    # Con la suya: vuelve a la misma pantalla y la gestión sensible queda habilitada
    r1 = c.get(f"{API}/auth/google/reautenticacion", params={"volver": "/admin/usuarios"}, follow_redirects=False)
    q1 = {k: v[0] for k, v in parse_qs(urlsplit(r1.headers["location"]).query).items()}
    r, _ = _volver_de_google(c, google_activo, q1, sub="g-ana", email="ana@gmail.com")
    assert r.status_code == 303 and r.headers["location"] == "/admin/usuarios"
    assert _claims(c)["amr"] == AMR_GOOGLE and abs(_claims(c)["auth_time"] - time.time()) < 10
    assert c.post(f"{API}/usuarios", json={"username": "xx2", "rol": "Vendedora",
                                            "password": "clave-segura-123"}).status_code == 201


def test_reautenticar_con_google_exige_estar_en_sesion(google_activo):
    assert Cliente(app).get(f"{API}/auth/google/reautenticacion", follow_redirects=False).status_code == 401


def test_un_admin_puede_desvincular_la_cuenta_de_google(google_activo, como):
    como(RolEnum.ADMIN, "jefe")
    admin = login("jefe")
    ana = _usuario("ana", RolEnum.VENDEDORA, email="ana@gmail.com")
    c = Cliente(app)
    _, q, _ = _iniciar(c)
    _volver_de_google(c, google_activo, q)
    assert admin.get(f"{API}/usuarios").json()
    assert next(u for u in admin.get(f"{API}/usuarios").json() if u["id"] == ana.id)["google_vinculado"] is True
    r = admin.delete(f"{API}/usuarios/{ana.id}/google")
    assert r.status_code == 200 and r.json()["google_vinculado"] is False
    assert c.get(f"{API}/auth/me").status_code == 401  # cierra sus sesiones
    assert admin.delete(f"{API}/usuarios/{ana.id}/google").status_code == 409


# ---------- Configuración ----------


def test_en_produccion_el_pepper_es_obligatorio():
    base = {"database_url": "sqlite:///x.db", "jwt_secret": "x" * 40, "env": "production",
            "cookie_secure": True, "cookie_prefix": "__Host-"}
    with pytest.raises(Exception, match="PIN_PEPPER"):
        config.Settings(**base)
    with pytest.raises(Exception, match="PIN_PEPPER"):
        config.Settings(**base, pin_pepper="corto")
    assert config.Settings(**base, pin_pepper="p" * 32).pin_pepper == "p" * 32


def test_google_exige_secreto_y_url_de_retorno_y_acepta_valores_vacios():
    base = {"database_url": "sqlite:///x.db", "jwt_secret": "x" * 40}
    with pytest.raises(Exception, match="GOOGLE_CLIENT_SECRET"):
        config.Settings(**base, google_client_id="abc")
    s = config.Settings(**base, google_client_id="", google_client_secret="", oauth_redirect_url=" ", pin_pepper="")
    assert s.google_habilitado is False and s.pin_pepper is None
    assert config.Settings(**base, google_client_ids_movil="a, b").google_client_ids_movil == ["a", "b"]
    s = config.Settings(**base, terminal_cookie_name="panaderia_terminal", cookie_prefix="__Host-", cookie_secure=True)
    assert s.terminal_cookie_name == "__Host-panaderia_terminal" and s.oauth_cookie_name == "__Host-panaderia_oauth"
