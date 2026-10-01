"""Código de producto, variantes "día anterior" y la conversión manual de la encargada."""

from datetime import timedelta

from app.db.base import utcnow
from app.models import ConversionDiaAnterior, Producto, RolEnum

API = "/api/v1"


def _variante(admin, base_id, nombre="Variante (día anterior)", precio=70):
    r = admin.post(f"{API}/productos", json={
        "nombre": nombre, "precio_venta": precio, "producto_base_id": base_id})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _stocks(c):
    return {p["id"]: p["stock_mostrador"] for p in c.get(f"{API}/productos").json()}


def _pasar(c, items, motivo=None):
    body = {"items": [{"producto_id": p, "cantidad": n} for p, n in items]}
    if motivo:
        body["motivo"] = motivo
    return c.post(f"{API}/stock/dia-anterior", json=body)


# ---------- Código y variante ----------


def test_codigo_unico_y_normalizado(como):
    admin = como(RolEnum.ADMIN)
    r = admin.post(f"{API}/productos", json={"nombre": "A", "precio_venta": 1, "codigo": " ab-12 "})
    assert r.status_code == 201
    assert r.json()["codigo"] == "AB-12"
    dup = admin.post(f"{API}/productos", json={"nombre": "B", "precio_venta": 1, "codigo": "ab-12"})
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "codigo_duplicado"
    otro = admin.post(f"{API}/productos", json={"nombre": "C", "precio_venta": 1})
    assert admin.patch(f"{API}/productos/{otro.json()['id']}", json={"codigo": "AB-12"}).status_code == 409


def test_codigo_invalido(como):
    admin = como(RolEnum.ADMIN)
    r = admin.post(f"{API}/productos", json={"nombre": "A", "precio_venta": 1, "codigo": "con espacio"})
    assert r.status_code == 422


def test_se_puede_quedar_con_el_mismo_codigo_al_editar(como):
    admin = como(RolEnum.ADMIN)
    pid = admin.post(f"{API}/productos", json={"nombre": "A", "precio_venta": 1, "codigo": "X1"}).json()["id"]
    r = admin.patch(f"{API}/productos/{pid}", json={"codigo": "X1", "nombre": "A2"})
    assert r.status_code == 200 and r.json()["nombre"] == "A2"
    assert admin.patch(f"{API}/productos/{pid}", json={"codigo": None}).json()["codigo"] is None


def test_una_sola_variante_por_producto_y_sin_cadenas(como, catalogo):
    admin = como(RolEnum.ADMIN)
    variante = _variante(admin, catalogo["pan"])
    dup = admin.post(f"{API}/productos", json={
        "nombre": "Otra", "precio_venta": 50, "producto_base_id": catalogo["pan"]})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "variante_duplicada"

    cadena = admin.post(f"{API}/productos", json={
        "nombre": "Variante de variante", "precio_venta": 50, "producto_base_id": variante})
    assert cadena.status_code == 409 and cadena.json()["error"]["code"] == "variante_invalida"

    # Un producto que ya tiene variante no puede volverse variante de otro
    r = admin.patch(f"{API}/productos/{catalogo['pan']}", json={"producto_base_id": catalogo["medialuna"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "variante_invalida"
    # ni de sí mismo
    r = admin.patch(f"{API}/productos/{catalogo['medialuna']}", json={"producto_base_id": catalogo["medialuna"]})
    assert r.status_code == 409


def test_base_inexistente(como):
    admin = como(RolEnum.ADMIN)
    r = admin.post(f"{API}/productos", json={"nombre": "X", "precio_venta": 1, "producto_base_id": 9999})
    assert r.status_code == 404


# ---------- Pasar a día anterior ----------


def test_pasar_a_dia_anterior_mueve_stock_y_audita(como, catalogo):
    admin = como(RolEnum.ADMIN)
    variante = _variante(admin, catalogo["pan"])
    r = _pasar(admin, [(catalogo["pan"], 4)], motivo="Sobró de ayer")
    assert r.status_code == 201, r.text
    assert _stocks(admin)[catalogo["pan"]] == 6
    assert _stocks(admin)[variante] == 4

    cuerpo = r.json()
    fila = next(p for p in cuerpo["productos"] if p["producto_id"] == catalogo["pan"])
    assert (fila["stock_mostrador"], fila["variante_stock"], fila["variante_id"]) == (6, 4, variante)
    conv = cuerpo["conversiones_hoy"][0]
    assert (conv["producto_id"], conv["cantidad"], conv["motivo"]) == (catalogo["pan"], 4, "Sobró de ayer")
    assert conv["se_puede_revertir"] is True and conv["revierte_id"] is None


def test_la_variante_se_vende_como_cualquier_producto(como, catalogo):
    admin = como(RolEnum.ADMIN)
    variante = _variante(admin, catalogo["pan"], precio=70)
    _pasar(admin, [(catalogo["pan"], 4)])
    vendedora = como(RolEnum.VENDEDORA)
    vendedora.post(f"{API}/turnos", json={"efectivo_inicial": 0})
    r = vendedora.post(f"{API}/ventas", json={"items": [{"producto_id": variante, "cantidad": 3}]})
    assert r.status_code == 201 and r.json()["monto"] == 210.0
    assert _stocks(admin)[variante] == 1


def test_todo_o_nada(como, catalogo):
    admin = como(RolEnum.ADMIN)
    _variante(admin, catalogo["pan"], "Pan (día anterior)")
    _variante(admin, catalogo["medialuna"], "Medialuna (día anterior)")
    # El pan alcanza (10) pero la medialuna no (hay 5): no se mueve nada
    r = _pasar(admin, [(catalogo["pan"], 4), (catalogo["medialuna"], 99)])
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "stock_insuficiente"
    assert [d["producto_id"] for d in r.json()["error"]["details"]] == [catalogo["medialuna"]]
    assert _stocks(admin)[catalogo["pan"]] == 10
    assert admin.get(f"{API}/stock/dia-anterior").json()["conversiones_hoy"] == []


def test_producto_sin_variante(como, catalogo):
    admin = como(RolEnum.ADMIN)
    r = _pasar(admin, [(catalogo["medialuna"], 1)])
    assert r.status_code == 409 and r.json()["error"]["code"] == "sin_variante"


def test_no_se_puede_pasar_una_variante(como, catalogo):
    admin = como(RolEnum.ADMIN)
    variante = _variante(admin, catalogo["pan"])
    _pasar(admin, [(catalogo["pan"], 2)])
    r = _pasar(admin, [(variante, 1)])
    assert r.status_code == 409 and r.json()["error"]["code"] == "sin_variante"


def test_cantidades_invalidas(como, catalogo):
    admin = como(RolEnum.ADMIN)
    _variante(admin, catalogo["pan"])
    assert _pasar(admin, [(catalogo["pan"], 0)]).status_code == 422
    assert _pasar(admin, [(catalogo["pan"], -3)]).status_code == 422
    assert admin.post(f"{API}/stock/dia-anterior", json={"items": []}).status_code == 422


def test_items_repetidos_se_suman(como, catalogo):
    admin = como(RolEnum.ADMIN)
    variante = _variante(admin, catalogo["pan"])
    r = _pasar(admin, [(catalogo["pan"], 3), (catalogo["pan"], 4)])
    assert r.status_code == 201
    assert _stocks(admin)[variante] == 7
    assert len(r.json()["conversiones_hoy"]) == 1


# ---------- Stock reservado (lo usa el reparto, Fase 2) ----------


def test_no_toma_stock_reservado(como, catalogo, db):
    admin = como(RolEnum.ADMIN)
    _variante(admin, catalogo["pan"])
    db.get(Producto, catalogo["pan"]).stock_reservado = 8  # 10 en mostrador, 8 comprometidas
    db.commit()

    r = _pasar(admin, [(catalogo["pan"], 3)])  # solo hay 2 disponibles
    assert r.status_code == 409
    detalle = r.json()["error"]["details"][0]
    assert (detalle["disponible"], detalle["solicitado"]) == (2, 3)
    assert _pasar(admin, [(catalogo["pan"], 2)]).status_code == 201


def test_la_caja_tampoco_vende_lo_reservado(como, catalogo, db):
    db.get(Producto, catalogo["pan"]).stock_reservado = 9
    db.commit()
    vendedora = como(RolEnum.VENDEDORA)
    vendedora.post(f"{API}/turnos", json={"efectivo_inicial": 0})
    r = vendedora.post(f"{API}/ventas", json={"items": [{"producto_id": catalogo["pan"], "cantidad": 2}]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "stock_insuficiente"
    ok = vendedora.post(f"{API}/ventas", json={"items": [{"producto_id": catalogo["pan"], "cantidad": 1}]})
    assert ok.status_code == 201


def test_ajuste_manual_no_puede_dejar_menos_que_lo_reservado(como, catalogo, db):
    db.get(Producto, catalogo["pan"]).stock_reservado = 8
    db.commit()
    admin = como(RolEnum.ADMIN)
    r = admin.put(f"{API}/productos/{catalogo['pan']}/stock", json={"stock_mostrador": 5})
    assert r.status_code == 409 and r.json()["error"]["code"] == "stock_menor_a_reservado"
    assert admin.put(f"{API}/productos/{catalogo['pan']}/stock", json={"stock_mostrador": 8}).status_code == 200


# ---------- Reversión ----------


def test_reversion_el_mismo_dia(como, catalogo):
    admin = como(RolEnum.ADMIN)
    variante = _variante(admin, catalogo["pan"])
    conv_id = _pasar(admin, [(catalogo["pan"], 4)]).json()["conversiones_hoy"][0]["id"]

    r = admin.post(f"{API}/stock/dia-anterior/{conv_id}/reversion")
    assert r.status_code == 200, r.text
    assert _stocks(admin)[catalogo["pan"]] == 10 and _stocks(admin)[variante] == 0

    hoy = {c["id"]: c for c in r.json()["conversiones_hoy"]}
    assert hoy[conv_id]["revertida"] is True and hoy[conv_id]["se_puede_revertir"] is False
    reversion = next(c for c in hoy.values() if c["revierte_id"] == conv_id)
    assert reversion["se_puede_revertir"] is False and reversion["cantidad"] == 4

    # Una conversión se revierte una sola vez, y una reversión no se revierte
    again = admin.post(f"{API}/stock/dia-anterior/{conv_id}/reversion")
    assert again.status_code == 409 and again.json()["error"]["code"] == "conversion_ya_revertida"
    rev_de_rev = admin.post(f"{API}/stock/dia-anterior/{reversion['id']}/reversion")
    assert rev_de_rev.status_code == 409
    assert rev_de_rev.json()["error"]["code"] == "conversion_no_revertible"


def test_reversion_necesita_que_la_variante_conserve_el_stock(como, catalogo):
    admin = como(RolEnum.ADMIN)
    variante = _variante(admin, catalogo["pan"])
    conv_id = _pasar(admin, [(catalogo["pan"], 4)]).json()["conversiones_hoy"][0]["id"]
    vendedora = como(RolEnum.VENDEDORA)
    vendedora.post(f"{API}/turnos", json={"efectivo_inicial": 0})
    vendedora.post(f"{API}/ventas", json={"items": [{"producto_id": variante, "cantidad": 3}]})

    r = admin.post(f"{API}/stock/dia-anterior/{conv_id}/reversion")  # quedó 1, se pedían 4
    assert r.status_code == 409 and r.json()["error"]["code"] == "stock_insuficiente"
    assert _stocks(admin)[catalogo["pan"]] == 6 and _stocks(admin)[variante] == 1


def test_reversion_de_otro_dia_no_se_permite(como, catalogo, db):
    admin = como(RolEnum.ADMIN)
    _variante(admin, catalogo["pan"])
    conv_id = _pasar(admin, [(catalogo["pan"], 4)]).json()["conversiones_hoy"][0]["id"]
    db.get(ConversionDiaAnterior, conv_id).fecha = utcnow() - timedelta(days=1, hours=2)
    db.commit()
    r = admin.post(f"{API}/stock/dia-anterior/{conv_id}/reversion")
    assert r.status_code == 409 and r.json()["error"]["code"] == "conversion_vencida"
    # y las de ayer ya no figuran entre las de hoy
    assert admin.get(f"{API}/stock/dia-anterior").json()["conversiones_hoy"] == []


def test_reversion_inexistente(como):
    assert como(RolEnum.ADMIN).post(f"{API}/stock/dia-anterior/9999/reversion").status_code == 404


def test_las_conversiones_no_se_modifican(como, catalogo):
    """Libro de auditoría: no hay rutas para editar ni borrar una conversión."""
    admin = como(RolEnum.ADMIN)
    _variante(admin, catalogo["pan"])
    conv_id = _pasar(admin, [(catalogo["pan"], 1)]).json()["conversiones_hoy"][0]["id"]
    assert admin.delete(f"{API}/stock/dia-anterior/{conv_id}").status_code in (404, 405)
    assert admin.patch(f"{API}/stock/dia-anterior/{conv_id}", json={"cantidad": 9}).status_code in (404, 405)


# ---------- Permisos ----------


def test_solo_gestion_pasa_a_dia_anterior(como, catalogo):
    admin = como(RolEnum.ADMIN)
    _variante(admin, catalogo["pan"])
    conv_id = _pasar(admin, [(catalogo["pan"], 1)]).json()["conversiones_hoy"][0]["id"]
    for rol in (RolEnum.VENDEDORA, RolEnum.PANADERO):
        c = como(rol)
        assert c.get(f"{API}/stock/dia-anterior").status_code == 403
        assert _pasar(c, [(catalogo["pan"], 1)]).status_code == 403
        assert c.post(f"{API}/stock/dia-anterior/{conv_id}/reversion").status_code == 403
    assert como(RolEnum.ENCARGADA).get(f"{API}/stock/dia-anterior").status_code == 200
