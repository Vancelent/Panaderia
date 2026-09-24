from app.models import RolEnum

API = "/api/v1"


def _abrir(c, monto=1000):
    r = c.post(f"{API}/turnos", json={"efectivo_inicial": monto})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_turno_unico_por_usuario(como):
    c = como(RolEnum.VENDEDORA)
    assert c.get(f"{API}/turnos/actual").json() is None
    _abrir(c)
    r = c.post(f"{API}/turnos", json={"efectivo_inicial": 5})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "turno_ya_abierto"


def test_fondo_negativo_rechazado(como):
    c = como(RolEnum.VENDEDORA)
    assert c.post(f"{API}/turnos", json={"efectivo_inicial": -10}).status_code == 422


def test_venta_sin_turno(como, catalogo):
    c = como(RolEnum.VENDEDORA)
    r = c.post(f"{API}/ventas", json={"items": [{"producto_id": catalogo["pan"], "cantidad": 1}]})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "sin_turno"


def test_venta_calcula_precios_en_servidor_y_descuenta_stock(como, catalogo):
    c = como(RolEnum.VENDEDORA)
    _abrir(c)
    r = c.post(f"{API}/ventas", json={
        "metodo_pago": "Tarjeta",
        # El cliente intenta mandar un total y un turno: se ignoran
        "total": 1, "turno_id": 999,
        "items": [{"producto_id": catalogo["pan"], "cantidad": 2},
                  {"producto_id": catalogo["pan"], "cantidad": 1},
                  {"producto_id": catalogo["medialuna"], "cantidad": 1}],
    })
    assert r.status_code == 201, r.text
    venta = r.json()
    assert venta["monto"] == 381.5  # 3 * 100.50 + 80
    assert venta["metodo_pago"] == "Tarjeta"
    assert {d["producto_id"]: d["cantidad"] for d in venta["detalles"]} == {
        catalogo["pan"]: 3, catalogo["medialuna"]: 1}
    stock = {p["id"]: p["stock_mostrador"] for p in c.get(f"{API}/productos").json()}
    assert stock[catalogo["pan"]] == 7
    assert stock[catalogo["medialuna"]] == 4


def test_cantidad_negativa_rechazada(como, catalogo):
    """Antes una venta con cantidad -10 sumaba stock y restaba dinero de la caja."""
    c = como(RolEnum.VENDEDORA)
    _abrir(c)
    r = c.post(f"{API}/ventas", json={"items": [{"producto_id": catalogo["pan"], "cantidad": -10}]})
    assert r.status_code == 422
    assert c.post(f"{API}/ventas", json={"items": []}).status_code == 422


def test_stock_insuficiente_no_descuenta_nada(como, catalogo):
    c = como(RolEnum.VENDEDORA)
    _abrir(c)
    r = c.post(f"{API}/ventas", json={"items": [
        {"producto_id": catalogo["pan"], "cantidad": 2},
        {"producto_id": catalogo["medialuna"], "cantidad": 50}]})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "stock_insuficiente"
    stock = {p["id"]: p["stock_mostrador"] for p in c.get(f"{API}/productos").json()}
    assert stock[catalogo["pan"]] == 10


def test_arqueo_ciego(como, catalogo):
    vendedora = como(RolEnum.VENDEDORA)
    admin = como(RolEnum.ADMIN)
    turno_id = _abrir(vendedora, 1000)
    vendedora.post(f"{API}/ventas", json={"metodo_pago": "Efectivo",
                                           "items": [{"producto_id": catalogo["pan"], "cantidad": 2}]})
    vendedora.post(f"{API}/ventas", json={"metodo_pago": "Transferencia",
                                           "items": [{"producto_id": catalogo["medialuna"], "cantidad": 1}]})

    r = vendedora.post(f"{API}/turnos/actual/cierre", json={"monto_declarado": 1190})
    assert r.status_code == 200
    cuerpo = r.json()
    assert "diferencia" not in cuerpo and "monto_sistema" not in cuerpo
    assert vendedora.get(f"{API}/arqueos").status_code == 403

    arqueo = admin.get(f"{API}/arqueos").json()[0]
    assert arqueo["turno_id"] == turno_id
    # Esperado en caja: 1000 + 201 (efectivo). La transferencia no entra al cajón.
    assert arqueo["monto_sistema"] == 1201
    assert arqueo["ventas_otros_medios"] == 80
    assert arqueo["diferencia"] == -11


def test_no_se_puede_cerrar_turno_ajeno_sin_ser_gestion(como):
    v1 = como(RolEnum.VENDEDORA)
    v2 = como(RolEnum.VENDEDORA)
    turno_id = _abrir(v1)
    r = v2.post(f"{API}/turnos/{turno_id}/cierre", json={"monto_declarado": 0})
    assert r.status_code == 403
