from app.models import RolEnum

API = "/api/v1"


def _stock(c):
    return {p["id"]: p["stock_mostrador"] for p in c.get(f"{API}/productos").json()}


def _insumos(c):
    return {m["id"]: m["stock_actual"] for m in c.get(f"{API}/materias-primas").json()}


def test_produccion_descuenta_insumos_por_receta(como, catalogo):
    c = como(RolEnum.PANADERO)
    r = c.post(f"{API}/produccion", json={"lotes": [
        {"producto_id": catalogo["pan"], "cantidad": 20},
        {"producto_id": catalogo["medialuna"], "cantidad": 5}]})
    assert r.status_code == 201, r.text
    assert r.json()["unidades_totales"] == 25
    assert _stock(c)[catalogo["pan"]] == 30
    assert _insumos(c)[catalogo["harina"]] == 5.0  # 10 kg - 20 * 0.25


def test_produccion_sin_insumos_no_registra_nada(como, catalogo):
    c = como(RolEnum.PANADERO)
    r = c.post(f"{API}/produccion", json={"lotes": [
        {"producto_id": catalogo["medialuna"], "cantidad": 5},
        {"producto_id": catalogo["pan"], "cantidad": 100}]})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "insumo_insuficiente"
    assert _stock(c)[catalogo["medialuna"]] == 5
    assert _insumos(c)[catalogo["harina"]] == 10.0


def test_merma(como, catalogo):
    c = como(RolEnum.VENDEDORA)
    r = c.post(f"{API}/mermas", json={"producto_id": catalogo["pan"], "cantidad_perdida": 3,
                                      "motivo": "Se cayó la bandeja"})
    assert r.status_code == 201
    assert _stock(c)[catalogo["pan"]] == 7
    r = c.post(f"{API}/mermas", json={"producto_id": catalogo["pan"], "cantidad_perdida": 50,
                                      "motivo": "x"})
    assert r.status_code == 409


def test_receta_y_costo(como, catalogo):
    admin = como(RolEnum.ADMIN)
    r = admin.get(f"{API}/productos/{catalogo['pan']}/receta")
    assert r.json()["costo_unitario"] == 125.0  # 0.25 kg * $500
    r = admin.put(f"{API}/productos/{catalogo['pan']}/receta", json={"insumos": [
        {"materia_prima_id": catalogo["harina"], "cantidad_necesaria": 0.5}]})
    assert r.status_code == 200
    assert r.json()["costo_unitario"] == 250.0


def test_compra_actualiza_stock_y_costo_promedio(como, catalogo):
    admin = como(RolEnum.ADMIN)
    prov = admin.post(f"{API}/proveedores", json={"nombre": "Molino SA", "cuit": "30-12345678-9"}).json()
    r = admin.post(f"{API}/compras", json={"proveedor_id": prov["id"], "materia_prima_id": catalogo["harina"],
                                           "cantidad_comprada": 10, "precio_total": 7000})
    assert r.status_code == 201, r.text
    mp = next(m for m in admin.get(f"{API}/materias-primas").json() if m["id"] == catalogo["harina"])
    assert mp["stock_actual"] == 20.0
    # (10 kg * 500 + 7000) / 20 kg = 600
    assert mp["costo_unitario_actual"] == 600.0


def test_compra_con_cantidad_cero_rechazada(como, catalogo):
    admin = como(RolEnum.ADMIN)
    r = admin.post(f"{API}/compras", json={"proveedor_id": 1, "materia_prima_id": catalogo["harina"],
                                           "cantidad_comprada": 0, "precio_total": 10})
    assert r.status_code == 422


def test_producto_inactivo_no_se_vende(como, catalogo):
    admin = como(RolEnum.ADMIN)
    admin.patch(f"{API}/productos/{catalogo['medialuna']}", json={"activo": False})
    vendedora = como(RolEnum.VENDEDORA)
    assert catalogo["medialuna"] not in _stock(vendedora)
    vendedora.post(f"{API}/turnos", json={"efectivo_inicial": 0})
    r = vendedora.post(f"{API}/ventas", json={"items": [{"producto_id": catalogo["medialuna"], "cantidad": 1}]})
    assert r.status_code == 409


def test_resumen_financiero(como, catalogo):
    v = como(RolEnum.VENDEDORA)
    v.post(f"{API}/turnos", json={"efectivo_inicial": 0})
    v.post(f"{API}/ventas", json={"items": [{"producto_id": catalogo["pan"], "cantidad": 2}]})
    admin = como(RolEnum.ADMIN)
    admin.post(f"{API}/gastos", json={"concepto": "Luz", "monto": 50})
    r = admin.get(f"{API}/finanzas/resumen")
    assert r.status_code == 200
    res = r.json()
    assert res["ventas_totales"] == 201.0
    assert res["cantidad_ventas"] == 1
    assert res["gastos_operativos"] == 50.0
    assert res["resultado"] == 151.0
    assert len(res["ventas_diarias"]) == 30
    assert res["top_productos"][0]["nombre"] == "Pan"


def test_errores_de_validacion_con_formato_unificado(como):
    admin = como(RolEnum.ADMIN)
    r = admin.post(f"{API}/productos", json={"nombre": "", "precio_venta": -5})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "validation_error"
    assert {d["campo"] for d in err["details"]} == {"nombre", "precio_venta"}
