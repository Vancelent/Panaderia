import jwt

from app.models import RolEnum
from tests.conftest import PASSWORD, Cliente, app, crear_usuario, login

API = "/api/v1"


def test_login_setea_cookie_httponly_y_no_devuelve_token(anonimo):
    crear_usuario("pamela", RolEnum.VENDEDORA)
    r = anonimo.post(f"{API}/auth/login", json={"username": "Pamela", "password": PASSWORD})
    assert r.status_code == 200
    assert r.json()["rol"] == "Vendedora"
    assert "access_token" not in r.json()
    set_cookie = " ".join(r.headers.get_list("set-cookie"))
    assert "panaderia_session=" in set_cookie
    assert "HttpOnly" in set_cookie.split("panaderia_csrf")[0]
    assert "SameSite=strict" in set_cookie


def test_credenciales_invalidas_mismo_mensaje(anonimo):
    crear_usuario("nelly", RolEnum.ADMIN)
    r1 = anonimo.post(f"{API}/auth/login", json={"username": "nelly", "password": "incorrecta"})
    r2 = anonimo.post(f"{API}/auth/login", json={"username": "nadie", "password": "incorrecta"})
    assert r1.status_code == r2.status_code == 401
    assert r1.json()["error"]["message"] == r2.json()["error"]["message"]


def test_rate_limit_login(anonimo):
    crear_usuario("nelly", RolEnum.ADMIN)
    for _ in range(5):
        anonimo.post(f"{API}/auth/login", json={"username": "nelly", "password": "mala"})
    r = anonimo.post(f"{API}/auth/login", json={"username": "nelly", "password": PASSWORD})
    assert r.status_code == 429


def test_me_requiere_sesion(anonimo):
    r = anonimo.get(f"{API}/auth/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_csrf_obligatorio_en_escrituras_con_cookie(como):
    c = como(RolEnum.VENDEDORA)
    r = c.post(f"{API}/turnos", json={"efectivo_inicial": 100}, headers={"X-CSRF-Token": "falso"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_failed"
    # Con el token correcto (el cliente lo reenvía solo) funciona
    assert c.post(f"{API}/turnos", json={"efectivo_inicial": 100}).status_code == 201


def test_token_falsificado_con_otra_clave_es_rechazado(anonimo):
    u = crear_usuario("nelly", RolEnum.ADMIN)
    falso = jwt.encode({"sub": str(u.id), "ver": 0, "exp": 9999999999},
                       "panaderia_secreta_super_segura_no_usar_en_prod", algorithm="HS256")
    r = anonimo.get(f"{API}/usuarios", headers={"Authorization": f"Bearer {falso}"})
    assert r.status_code == 401


def test_alg_none_rechazado(anonimo):
    u = crear_usuario("nelly", RolEnum.ADMIN)
    falso = jwt.encode({"sub": str(u.id), "ver": 0, "exp": 9999999999}, None, algorithm="none")
    r = anonimo.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {falso}"})
    assert r.status_code == 401


def test_bearer_token_para_clientes_api(anonimo):
    crear_usuario("nelly", RolEnum.ADMIN)
    r = anonimo.post(f"{API}/auth/token", data={"username": "nelly", "password": PASSWORD})
    token = r.json()["access_token"]
    c = Cliente(app)
    assert c.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_logout_limpia_cookies(como):
    c = como(RolEnum.PANADERO)
    assert c.post(f"{API}/auth/logout").status_code == 200
    assert c.get(f"{API}/auth/me").status_code == 401


def test_cambiar_password_invalida_otras_sesiones(como):
    c1 = como(RolEnum.VENDEDORA, "pamela")
    c2 = login("pamela")
    r = c1.post(f"{API}/auth/cambiar-password",
                json={"password_actual": PASSWORD, "password_nueva": "otra-clave-456"})
    assert r.status_code == 200
    assert c1.get(f"{API}/auth/me").status_code == 200  # la sesión actual se renueva
    assert c2.get(f"{API}/auth/me").status_code == 401  # las demás caen


def test_usuario_desactivado_pierde_acceso(como):
    admin = como(RolEnum.ADMIN)
    vendedora = como(RolEnum.VENDEDORA, "pamela")
    uid = vendedora.get(f"{API}/auth/me").json()["id"]
    assert admin.patch(f"{API}/usuarios/{uid}", json={"activo": False}).status_code == 200
    assert vendedora.get(f"{API}/auth/me").status_code == 401
