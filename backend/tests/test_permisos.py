"""Matriz de autorización: el backend es la única fuente de verdad sobre roles."""

import pytest

from app.models import RolEnum

API = "/api/v1"

PUBLICOS_PROHIBIDOS = [
    ("post", "/usuarios", {"username": "hacker", "rol": "Admin", "password": "12345678"}),
    ("get", "/finanzas/resumen", None),
    ("get", "/proveedores", None),
    ("post", "/compras", {"proveedor_id": 1, "materia_prima_id": 1, "cantidad_comprada": 1, "precio_total": 1}),
    ("post", "/gastos", {"concepto": "x", "monto": 1}),
    ("post", "/produccion", {"lotes": [{"producto_id": 1, "cantidad": 999}]}),
    ("get", "/arqueos", None),
    ("get", "/productos", None),
]


@pytest.mark.parametrize("metodo,ruta,body", PUBLICOS_PROHIBIDOS)
def test_endpoints_sin_sesion_devuelven_401(anonimo, metodo, ruta, body):
    r = getattr(anonimo, metodo)(API + ruta, **({"json": body} if body else {}))
    assert r.status_code == 401


SOLO_GESTION = [
    ("get", "/finanzas/resumen", None),
    ("get", "/arqueos", None),
    ("get", "/proveedores", None),
    ("post", "/gastos", {"concepto": "Luz", "monto": 10}),
    ("post", "/productos", {"nombre": "X", "precio_venta": 1}),
    ("get", "/turnos/abiertos", None),
]


@pytest.mark.parametrize("rol", [RolEnum.VENDEDORA, RolEnum.PANADERO])
@pytest.mark.parametrize("metodo,ruta,body", SOLO_GESTION)
def test_operativos_no_acceden_a_gestion(como, rol, metodo, ruta, body):
    c = como(rol)
    r = getattr(c, metodo)(API + ruta, **({"json": body} if body else {}))
    assert r.status_code == 403


@pytest.mark.parametrize("rol", [RolEnum.ENCARGADA, RolEnum.VENDEDORA, RolEnum.PANADERO])
def test_solo_admin_gestiona_usuarios(como, rol):
    c = como(rol)
    r = c.post(f"{API}/usuarios", json={"username": "nuevo", "rol": "Admin", "password": "12345678"})
    assert r.status_code == 403


def test_admin_crea_usuario_y_valida_password(como):
    admin = como(RolEnum.ADMIN)
    corta = admin.post(f"{API}/usuarios", json={"username": "nuevo", "rol": "Vendedora", "password": "123"})
    assert corta.status_code == 422
    ok = admin.post(f"{API}/usuarios", json={"username": "Nuevo", "rol": "Vendedora", "password": "12345678"})
    assert ok.status_code == 201
    assert ok.json()["username"] == "nuevo"
    assert "hashed_password" not in ok.json()


def test_no_se_puede_quitar_el_ultimo_admin(como):
    admin = como(RolEnum.ADMIN)
    uid = admin.get(f"{API}/auth/me").json()["id"]
    r = admin.patch(f"{API}/usuarios/{uid}", json={"rol": "Vendedora"})
    assert r.status_code == 409


def test_panadero_no_cobra(como):
    c = como(RolEnum.PANADERO)
    assert c.post(f"{API}/turnos", json={"efectivo_inicial": 0}).status_code == 403
    assert c.post(f"{API}/ventas", json={"items": [{"producto_id": 1, "cantidad": 1}]}).status_code == 403


def test_vendedora_no_produce(como, catalogo):
    c = como(RolEnum.VENDEDORA)
    r = c.post(f"{API}/produccion", json={"lotes": [{"producto_id": catalogo["pan"], "cantidad": 1}]})
    assert r.status_code == 403
