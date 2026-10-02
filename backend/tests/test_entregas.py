"""Reparto: hojas de ruta, reserva de stock, carga, entregas idempotentes, recorrido y rendición."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models import (
    Entrega,
    EntregaEvento,
    HojaRuta,
    Merma,
    MovimientoCuentaCorriente,
    OperacionIdempotente,
    Producto,
    RecorridoPunto,
    RolEnum,
    Turno,
    Venta,
)
from app.services import stock
from tests.conftest import crear_usuario, login

API = "/api/v1"
ENT = f"{API}/entregas"
CC = f"{API}/contabilidad"

CENTRO = ("-34.603700", "-58.381600")
NORTE = ("-34.580000", "-58.420000")


def ahora(**delta):
    return (datetime.now(UTC) - timedelta(**delta)).isoformat()


def pos(coord=CENTRO, **extra):
    return {"latitud": coord[0], "longitud": coord[1], "precision_m": "8.5", "registrado_en": ahora(), **extra}


def op(**extra):
    return {"operacion_id": str(uuid.uuid4()), **extra}


def _hoja(r, *paradas, fecha=None):
    body = {
        "fecha": (fecha or stock.hoy_local()).isoformat(),
        "repartidor_id": r["repartidor_id"],
        "paradas": [
            {"punto_entrega_id": p["id"], "items": [{"producto_id": pid, "cantidad": c} for pid, c in items.items()]}
            for p, items in paradas
        ],
    }
    resp = r["admin"].post(f"{ENT}/hojas", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _confirmar(r, hoja_id):
    return r["admin"].post(f"{ENT}/hojas/{hoja_id}/confirmacion")


def _cargar(r, hoja_id, items=None, fondo=500, quien="admin"):
    return r[quien].post(f"{ENT}/hojas/{hoja_id}/carga", json={"items": items or [], "fondo_inicial": fondo})


def _salir(r, hoja_id, **extra):
    body = op(ubicacion_concedida=True, posicion=pos(), **extra)
    return r["repa"].post(f"{ENT}/hojas/{hoja_id}/inicio-ruta", json=body)


def _en_ruta(r, *paradas, items_carga=None, fondo=500):
    hoja = _hoja(r, *paradas)
    assert _confirmar(r, hoja["id"]).status_code == 200
    resp = _cargar(r, hoja["id"], items_carga, fondo)
    assert resp.status_code == 200, resp.text
    resp = _salir(r, hoja["id"])
    assert resp.status_code == 200, resp.text
    return resp.json()


def _entrega(hoja, nombre):
    return next(e for e in hoja["entregas"] if e["punto_nombre"] == nombre)


def _confirmacion(items, pagos=None, **extra):
    return {**op(posicion=pos()), "items": [{"producto_id": p, "cantidad_entregada": c} for p, c in items.items()],
            "pagos": pagos or [], **extra}


def _entregar(r, entrega_id, items, pagos=None, **extra):
    return r["repa"].post(f"{ENT}/{entrega_id}/confirmacion", json=_confirmacion(items, pagos, **extra))


def _producto(c, pid):
    return next(p for p in c.get(f"{API}/productos").json() if p["id"] == pid)


def _codigo(resp):
    return resp.json()["error"]["code"]


def _abrir_caja(como, monto=0):
    caja = como(RolEnum.VENDEDORA)
    assert caja.post(f"{API}/turnos", json={"efectivo_inicial": monto}).status_code == 201
    return caja


# ---------- La caja no vende lo reservado ----------


def test_la_caja_no_puede_vender_stock_reservado(reparto, como):
    r, pan = reparto, reparto["pan"]
    admin = r["admin"]
    admin.put(f"{API}/productos/{pan}/stock", json={"stock_mostrador": 10})
    hoja = _hoja(r, (r["centro"], {pan: 8}))
    assert _confirmar(r, hoja["id"]).status_code == 200

    p = _producto(admin, pan)
    assert (p["stock_mostrador"], p["stock_reservado"], p["stock_disponible"]) == (10, 8, 2)

    caja = _abrir_caja(como)
    venta = lambda n: caja.post(f"{API}/ventas", json={"items": [{"producto_id": pan, "cantidad": n}]})  # noqa: E731
    sobrante = venta(3)
    assert sobrante.status_code == 409 and _codigo(sobrante) == "stock_insuficiente"
    assert sobrante.json()["error"]["details"][0]["disponible"] == 2

    assert venta(2).status_code == 201
    p = _producto(admin, pan)
    assert (p["stock_mostrador"], p["stock_reservado"], p["stock_disponible"]) == (8, 8, 0)
    assert venta(1).status_code == 409

    # Tampoco una merma puede consumir lo reservado, ni un conteo manual dejarlo por debajo
    merma = caja.post(f"{API}/mermas", json={"producto_id": pan, "cantidad_perdida": 1, "motivo": "Se cayó"})
    assert merma.status_code == 409 and _codigo(merma) == "stock_insuficiente"
    ajuste = admin.put(f"{API}/productos/{pan}/stock", json={"stock_mostrador": 5})
    assert ajuste.status_code == 409 and _codigo(ajuste) == "stock_menor_a_reservado"

    # Al reabrir la hoja, lo reservado vuelve a estar a la venta
    assert admin.post(f"{ENT}/hojas/{hoja['id']}/reapertura").status_code == 200
    assert _producto(admin, pan)["stock_disponible"] == 8
    assert venta(1).status_code == 201


def test_confirmar_sin_stock_suficiente_no_reserva_nada(reparto):
    r = reparto
    hoja = _hoja(r, (r["centro"], {r["pan"]: 10, r["medialuna"]: 60}))  # hay 50 medialunas
    resp = _confirmar(r, hoja["id"])
    assert resp.status_code == 409 and _codigo(resp) == "stock_insuficiente"
    faltante = resp.json()["error"]["details"]
    assert [(d["nombre"], d["disponible"], d["solicitado"]) for d in faltante] == [("Medialuna", 50, 60)]
    assert _producto(r["admin"], r["pan"])["stock_reservado"] == 0  # todo o nada
    assert r["admin"].get(f"{ENT}/hojas/{hoja['id']}").json()["estado"] == "Borrador"


def test_anular_libera_la_reserva(reparto):
    r = reparto
    hoja = _hoja(r, (r["centro"], {r["pan"]: 8}))
    _confirmar(r, hoja["id"])
    assert _producto(r["admin"], r["pan"])["stock_reservado"] == 8
    resp = r["admin"].post(f"{ENT}/hojas/{hoja['id']}/anulacion")
    assert resp.status_code == 200 and resp.json()["estado"] == "Anulada"
    assert _producto(r["admin"], r["pan"])["stock_reservado"] == 0
    assert r["admin"].post(f"{ENT}/hojas/{hoja['id']}/anulacion").status_code == 409  # ya anulada
    assert _confirmar(r, hoja["id"]).status_code == 409


# ---------- Carga ----------


def test_la_carga_parcial_libera_la_diferencia_para_la_caja(reparto, como):
    r, pan, medialuna = reparto, reparto["pan"], reparto["medialuna"]
    admin = r["admin"]
    admin.put(f"{API}/productos/{pan}/stock", json={"stock_mostrador": 10})
    admin.put(f"{API}/productos/{medialuna}/stock", json={"stock_mostrador": 5})
    hoja = _hoja(r, (r["centro"], {pan: 8, medialuna: 4}))
    _confirmar(r, hoja["id"])

    resp = _cargar(r, hoja["id"], [{"producto_id": pan, "cantidad": 5}], fondo=300)
    assert resp.status_code == 200, resp.text
    cargada = resp.json()
    assert cargada["estado"] == "Cargada" and cargada["turno_id"] is not None
    assert {c["nombre"]: (c["reservada"], c["cargada"]) for c in cargada["carga"]} == {
        "Pan": (8, 5), "Medialuna": (4, 0),
    }

    p, m = _producto(admin, pan), _producto(admin, medialuna)
    assert (p["stock_mostrador"], p["stock_reservado"], p["stock_disponible"]) == (5, 0, 5)
    assert (m["stock_mostrador"], m["stock_reservado"], m["stock_disponible"]) == (5, 0, 5)

    # Lo que no salió ya lo puede vender la caja
    caja = _abrir_caja(como)
    assert caja.post(f"{API}/ventas", json={"items": [{"producto_id": medialuna, "cantidad": 5}]}).status_code == 201

    # El turno de reparto es de otro tipo que el de mostrador y lleva el fondo inicial
    abiertos = admin.get(f"{API}/turnos/abiertos").json()
    reparto_turno = next(t for t in abiertos if t["id"] == cargada["turno_id"])
    assert reparto_turno["tipo"] == "Reparto" and reparto_turno["efectivo_inicial"] == 300
    assert _codigo(_cargar(r, hoja["id"])) == "transicion_invalida"  # no se carga dos veces


def test_validaciones_de_la_carga(reparto):
    r, pan, medialuna = reparto, reparto["pan"], reparto["medialuna"]
    hoja = _hoja(r, (r["centro"], {pan: 5}))
    assert _cargar(r, hoja["id"]).status_code == 409  # todavía no está confirmada
    _confirmar(r, hoja["id"])

    mas = _cargar(r, hoja["id"], [{"producto_id": pan, "cantidad": 6}])
    assert mas.status_code == 409 and _codigo(mas) == "cantidad_excede_reserva"
    ajeno = _cargar(r, hoja["id"], [{"producto_id": medialuna, "cantidad": 1}])
    assert ajeno.status_code == 422 and _codigo(ajeno) == "producto_fuera_de_hoja"
    vacia = _cargar(r, hoja["id"], [{"producto_id": pan, "cantidad": 0}])
    assert vacia.status_code == 422 and _codigo(vacia) == "carga_vacia"
    # Los rechazos no tocaron el stock
    p = _producto(r["admin"], pan)
    assert (p["stock_mostrador"], p["stock_reservado"]) == (100, 5)


def test_un_repartidor_no_puede_tener_dos_hojas_cargadas(reparto):
    r, pan = reparto, reparto["pan"]
    a, b = _hoja(r, (r["centro"], {pan: 2})), _hoja(r, (r["norte"], {pan: 3}))
    _confirmar(r, a["id"]), _confirmar(r, b["id"])
    assert _cargar(r, a["id"]).status_code == 200
    resp = _cargar(r, b["id"])
    assert resp.status_code == 409 and _codigo(resp) == "turno_ya_abierto"
    p = _producto(r["admin"], pan)
    assert (p["stock_mostrador"], p["stock_reservado"]) == (98, 3)  # la segunda sigue reservada


def test_el_repartidor_carga_su_hoja_pero_no_la_de_otro(reparto):
    r, pan = reparto, reparto["pan"]
    crear_usuario("repa2", RolEnum.REPARTIDOR)
    otro = login("repa2")
    hoja = _hoja(r, (r["centro"], {pan: 2}))
    _confirmar(r, hoja["id"])
    assert _cargar({**r, "otro": otro}, hoja["id"], quien="otro").status_code == 403
    assert _cargar(r, hoja["id"], quien="repa").status_code == 200


# ---------- Sin ubicación no se sale a la ruta ----------


def test_sin_permiso_de_ubicacion_no_pasa_a_en_ruta(reparto):
    r, pan = reparto, reparto["pan"]
    hoja = _hoja(r, (r["centro"], {pan: 4}))
    _confirmar(r, hoja["id"])
    _cargar(r, hoja["id"])

    operacion = str(uuid.uuid4())
    rechazo = r["repa"].post(
        f"{ENT}/hojas/{hoja['id']}/inicio-ruta", json={"operacion_id": operacion, "ubicacion_concedida": False}
    )
    assert rechazo.status_code == 409 and _codigo(rechazo) == "hoja_sin_ubicacion"
    assert r["repa"].get(f"{ENT}/hojas/hoy").json()["estado"] == "Cargada"  # sigue sin salir

    # Y sin salir tampoco puede registrar entregas
    entrega = r["repa"].get(f"{ENT}/hojas/hoy").json()["entregas"][0]
    antes = r["repa"].post(f"{ENT}/{entrega['id']}/check-in", json=op(posicion=pos()))
    assert antes.status_code == 409 and _codigo(antes) == "transicion_invalida"
    assert _entregar(r, entrega["id"], {pan: 4}).status_code == 409

    # El rechazo no consumió la clave: la misma operación sale bien cuando se otorga el permiso
    ok = r["repa"].post(
        f"{ENT}/hojas/{hoja['id']}/inicio-ruta",
        json={"operacion_id": operacion, "ubicacion_concedida": True, "posicion": pos()},
    )
    assert ok.status_code == 200 and ok.json()["estado"] == "En ruta" and ok.json()["iniciada_en"]
    # Reintentar la misma operación devuelve lo mismo
    repetida = r["repa"].post(
        f"{ENT}/hojas/{hoja['id']}/inicio-ruta",
        json={"operacion_id": operacion, "ubicacion_concedida": True, "posicion": pos()},
    )
    assert repetida.status_code == 200 and repetida.json()["estado"] == "En ruta"
    # El punto de partida quedó como primer punto de la traza
    with SessionLocal() as s:
        assert s.scalar(select(func.count()).select_from(RecorridoPunto)) == 1


def test_no_se_inicia_la_ruta_sin_cargar_ni_ajena(reparto):
    r, pan = reparto, reparto["pan"]
    hoja = _hoja(r, (r["centro"], {pan: 4}))
    assert _salir(r, hoja["id"]).status_code == 409  # borrador
    _confirmar(r, hoja["id"])
    assert _salir(r, hoja["id"]).status_code == 409  # confirmada pero sin cargar
    crear_usuario("repa2", RolEnum.REPARTIDOR)
    ajeno = login("repa2").post(
        f"{ENT}/hojas/{hoja['id']}/inicio-ruta", json=op(ubicacion_concedida=True)
    )
    assert ajeno.status_code == 403
    assert r["admin"].post(
        f"{ENT}/hojas/{hoja['id']}/inicio-ruta", json=op(ubicacion_concedida=True)
    ).status_code == 403  # la gestión no sale a la ruta por el repartidor


# ---------- Entregas ----------


def test_flujo_de_entregas_con_cobro_remito_y_cuenta_corriente(reparto):
    r, pan, medialuna = reparto, reparto["pan"], reparto["medialuna"]
    hoja = _en_ruta(r, (r["centro"], {pan: 5}), (r["norte"], {medialuna: 3}))
    centro, norte = _entrega(hoja, "Centro"), _entrega(hoja, "Norte")
    assert centro["total"] == 502.5 and norte["total"] == 240

    # Norte primero, cobrando 100 en efectivo: lo demás queda a cuenta corriente
    resp = _entregar(r, norte["id"], {medialuna: 3}, pagos=[{"metodo_pago": "Efectivo", "monto": 100}],
                     recibio_nombre="Marta")
    assert resp.status_code == 200, resp.text
    e = resp.json()
    assert (e["estado"], e["numero_remito"], e["orden_real"]) == ("Entregada", 1, 1)
    assert (e["total"], e["cobrado"], e["saldo_cliente"]) == (240, 100, 140)

    # Centro, todo en efectivo
    resp = _entregar(r, centro["id"], {pan: 5}, pagos=[{"metodo_pago": "Efectivo", "monto": "502.50"}])
    assert resp.status_code == 200, resp.text
    e = resp.json()
    assert (e["numero_remito"], e["orden_real"], e["saldo_cliente"]) == (2, 2, 140)

    with SessionLocal() as s:
        turno_id = s.scalar(select(HojaRuta.turno_id).where(HojaRuta.id == hoja["id"]))
        ventas = s.scalars(select(Venta).order_by(Venta.id)).all()
        assert [(v.turno_id, v.origen.value, v.monto) for v in ventas] == [
            (turno_id, "Reparto", Decimal("240.00")), (turno_id, "Reparto", Decimal("502.50")),
        ]
        assert [v.punto_entrega_id for v in ventas] == [norte["punto_entrega_id"], centro["punto_entrega_id"]]
        medios = {(p.metodo_pago.value, p.monto) for p in ventas[0].pagos}
        assert medios == {("Efectivo", Decimal("100.00")), ("Cuenta corriente", Decimal("140.00"))}
        cargos = s.scalars(select(MovimientoCuentaCorriente)).all()
        assert [(m.tipo.value, m.importe, m.venta_id, m.punto_entrega_id) for m in cargos] == [
            ("Cargo", Decimal("140.00"), ventas[0].id, norte["punto_entrega_id"]),
        ]
        # Los precios y el stock no se vuelven a tocar al entregar: salieron del local en la carga
        assert s.scalar(select(Producto.stock_mostrador).where(Producto.id == pan)) == 95


def test_la_entrega_fuera_de_orden_asigna_orden_real(reparto):
    r, pan, medialuna = reparto, reparto["pan"], reparto["medialuna"]
    hoja = _en_ruta(r, (r["centro"], {pan: 1}), (r["norte"], {medialuna: 1}))
    primera, segunda = hoja["entregas"]  # orden sugerido
    assert (primera["orden_sugerido"], segunda["orden_sugerido"]) == (1, 2)
    # Se atiende la segunda antes que la primera: el orden sugerido no es obligatorio
    p2 = segunda["items"][0]["producto_id"]
    p1 = primera["items"][0]["producto_id"]
    assert _entregar(r, segunda["id"], {p2: 1}).json()["orden_real"] == 1
    assert _entregar(r, primera["id"], {p1: 1}).json()["orden_real"] == 2
    mapa = r["admin"].get(f"{ENT}/hojas/{hoja['id']}/recorrido").json()
    assert mapa["indicadores"]["entregas_fuera_de_orden"] == 2


def test_un_reintento_con_el_mismo_operacion_id_no_duplica(reparto):
    r, pan, medialuna = reparto, reparto["pan"], reparto["medialuna"]
    hoja = _en_ruta(r, (r["centro"], {pan: 5}), (r["norte"], {medialuna: 3}))
    centro, norte = _entrega(hoja, "Centro"), _entrega(hoja, "Norte")
    cuerpo = _confirmacion({pan: 5}, pagos=[{"metodo_pago": "Efectivo", "monto": 200}])

    primera = r["repa"].post(f"{ENT}/{centro['id']}/confirmacion", json=cuerpo)
    segunda = r["repa"].post(f"{ENT}/{centro['id']}/confirmacion", json=cuerpo)
    assert primera.status_code == segunda.status_code == 200
    assert primera.json() == segunda.json()
    assert primera.json()["saldo_cliente"] == 302.5

    with SessionLocal() as s:
        assert s.scalar(select(func.count()).select_from(Venta)) == 1
        assert s.scalar(select(func.count()).select_from(MovimientoCuentaCorriente)) == 1
        assert s.scalar(select(func.count()).select_from(EntregaEvento)) == 1
        assert s.scalar(select(Entrega.numero_remito).where(Entrega.id == centro["id"])) == 1

    # Una operación distinta sobre la misma entrega ya resuelta se rechaza
    otra = _entregar(r, centro["id"], {pan: 5})
    assert otra.status_code == 409 and _codigo(otra) == "entrega_cerrada"
    # Y la misma clave no sirve para otra entrega
    reuso = r["repa"].post(f"{ENT}/{norte['id']}/confirmacion", json={**_confirmacion({medialuna: 3}),
                                                                      "operacion_id": cuerpo["operacion_id"]})
    assert reuso.status_code == 409 and _codigo(reuso) == "operacion_en_curso"


def test_una_operacion_rechazada_no_consume_su_clave(reparto):
    r, pan = reparto, reparto["pan"]
    hoja = _en_ruta(r, (r["centro"], {pan: 5}))
    e = hoja["entregas"][0]
    cuerpo = _confirmacion({pan: 9})
    malo = r["repa"].post(f"{ENT}/{e['id']}/confirmacion", json=cuerpo)
    assert malo.status_code == 422 and _codigo(malo) == "cantidad_excede_planificada"
    with SessionLocal() as s:
        claves = s.scalars(select(OperacionIdempotente.tipo)).all()
        assert not any(t.startswith("confirmacion") for t in claves)  # solo quedó la de inicio-ruta
    cuerpo["items"] = [{"producto_id": pan, "cantidad_entregada": 5}]
    assert r["repa"].post(f"{ENT}/{e['id']}/confirmacion", json=cuerpo).status_code == 200


def test_entrega_parcial_check_in_y_no_entregada(reparto):
    r, pan, medialuna = reparto, reparto["pan"], reparto["medialuna"]
    hoja = _en_ruta(r, (r["centro"], {pan: 5, medialuna: 4}), (r["norte"], {pan: 2}))
    centro, norte = _entrega(hoja, "Centro"), _entrega(hoja, "Norte")

    ci = r["repa"].post(f"{ENT}/{centro['id']}/check-in", json=op(posicion=pos()))
    assert ci.status_code == 200 and ci.json()["estado"] == "En el local"
    again = r["repa"].post(f"{ENT}/{centro['id']}/check-in", json=op(posicion=pos()))
    assert again.status_code == 200 and again.json()["estado"] == "En el local"
    with SessionLocal() as s:
        assert s.scalar(select(func.count()).select_from(EntregaEvento)) == 1  # el segundo no suma

    parcial = _entregar(r, centro["id"], {pan: 5, medialuna: 3})
    assert parcial.status_code == 200
    e = parcial.json()
    assert e["estado"] == "Parcial" and e["total"] == 5 * 100.5 + 3 * 80
    assert {i["nombre"]: i["cantidad_entregada"] for i in e["items"]} == {"Pan": 5, "Medialuna": 3}
    assert e["saldo_cliente"] == e["total"]  # sin cobro: todo a cuenta corriente
    assert r["repa"].post(f"{ENT}/{centro['id']}/check-in", json=op()).status_code == 409  # ya resuelta

    no = r["repa"].post(f"{ENT}/{norte['id']}/no-entregada", json=op(motivo="Local cerrado", posicion=pos(NORTE)))
    assert no.status_code == 200
    n = no.json()
    assert (n["estado"], n["motivo_no_entrega"], n["numero_remito"], n["total"]) == (
        "No entregada", "Local cerrado", None, 0,
    )
    assert n["orden_real"] == 2
    assert _entregar(r, norte["id"], {pan: 2}).status_code == 409
    with SessionLocal() as s:
        assert s.scalar(select(func.count()).select_from(Venta)) == 1  # la no entregada no factura


def test_las_cantidades_no_pueden_superar_lo_cargado(reparto):
    r, pan = reparto, reparto["pan"]
    hoja = _en_ruta(r, (r["centro"], {pan: 10}), items_carga=[{"producto_id": pan, "cantidad": 3}])
    e = hoja["entregas"][0]
    resp = _entregar(r, e["id"], {pan: 5})
    assert resp.status_code == 409 and _codigo(resp) == "cantidad_excede_carga"
    assert resp.json()["error"]["details"][0] | {"nombre": "Pan"} == {
        "producto_id": pan, "nombre": "Pan", "cargado": 3, "ya_entregado": 0, "solicitado": 5,
    }
    ok = _entregar(r, e["id"], {pan: 3})
    assert ok.status_code == 200 and ok.json()["estado"] == "Parcial"


def test_validaciones_de_la_confirmacion(reparto):
    r, pan, medialuna = reparto, reparto["pan"], reparto["medialuna"]
    hoja = _en_ruta(r, (r["centro"], {pan: 5}))
    e = hoja["entregas"][0]
    casos = [
        ({pan: 6}, None, 422, "cantidad_excede_planificada"),
        ({pan: 0}, None, 422, "entrega_vacia"),
        ({medialuna: 1}, None, 422, "producto_fuera_de_entrega"),
        ({pan: 1}, [{"metodo_pago": "Efectivo", "monto": 200}], 422, "pago_excede_total"),
    ]
    for items, pagos, estado, codigo in casos:
        resp = _entregar(r, e["id"], items, pagos)
        assert resp.status_code == estado and _codigo(resp) == codigo, (items, resp.text)
    # No se informa la cuenta corriente como un pago: lo no cobrado se asigna solo
    mal = _entregar(r, e["id"], {pan: 5}, [{"metodo_pago": "Cuenta corriente", "monto": 10}])
    assert mal.status_code == 422
    assert r["repa"].post(f"{ENT}/{e['id']}/confirmacion", json={**op(), "items": []}).status_code == 422
    with SessionLocal() as s:
        assert s.scalar(select(func.count()).select_from(Venta)) == 0


def test_los_precios_se_congelan_al_confirmar_la_hoja(reparto):
    r, pan = reparto, reparto["pan"]
    admin, punto_id = r["admin"], r["centro"]["id"]
    d = admin.post(f"{CC}/puntos-entrega/{punto_id}/descuentos",
                   json={"producto_id": pan, "porcentaje": 10, "motivo": "Mayorista"})
    assert d.status_code == 201, d.text
    hoja = _hoja(r, (r["centro"], {pan: 10}))
    item = hoja["entregas"][0]["items"][0]
    assert (item["precio_lista"], item["descuento_pct"], item["precio_unitario"]) == (100.5, 10, 90.45)

    # Cambia el descuento antes de confirmar: se toma el vigente al confirmar
    admin.patch(f"{CC}/puntos-entrega/{punto_id}/descuentos/{d.json()['id']}", json={"porcentaje": 20})
    assert _confirmar(r, hoja["id"]).json()["entregas"][0]["items"][0]["precio_unitario"] == 80.4

    # Cambia después: la entrega ya está congelada
    admin.patch(f"{CC}/puntos-entrega/{punto_id}/descuentos/{d.json()['id']}", json={"porcentaje": 50})
    admin.patch(f"{API}/productos/{pan}", json={"precio_venta": 500})
    _cargar(r, hoja["id"])
    _salir(r, hoja["id"])
    e = r["repa"].get(f"{ENT}/hojas/hoy").json()["entregas"][0]
    resp = _entregar(r, e["id"], {pan: 10})
    assert resp.status_code == 200 and resp.json()["total"] == 804


def test_el_cobro_en_efectivo_cuenta_en_el_arqueo_del_reparto(reparto):
    r, pan = reparto, reparto["pan"]
    hoja = _en_ruta(r, (r["centro"], {pan: 10}), fondo=1000)
    e = hoja["entregas"][0]
    assert _entregar(r, e["id"], {pan: 6}, [
        {"metodo_pago": "Efectivo", "monto": 400}, {"metodo_pago": "Transferencia", "monto": 100, "referencia": "T-1"},
    ]).status_code == 200
    rend = r["admin"].post(f"{ENT}/hojas/{hoja['id']}/rendicion", json={
        "devoluciones": [{"producto_id": pan, "cantidad": 4, "destino": "Reingreso"}],
        "efectivo_declarado": 1395,
    })
    assert rend.status_code == 200, rend.text
    arqueo = r["admin"].get(f"{API}/arqueos").json()[0]
    assert arqueo["monto_sistema"] == 1400  # fondo 1000 + 400 en efectivo (la transferencia no entra al cajón)
    assert (arqueo["ventas_efectivo"], arqueo["ventas_otros_medios"]) == (400, 203)
    assert arqueo["diferencia"] == -5


# ---------- Rendición ----------


def test_rendicion_con_devoluciones_a_stock_y_a_merma(reparto):
    r, pan = reparto, reparto["pan"]
    hoja = _en_ruta(r, (r["centro"], {pan: 10}), (r["norte"], {pan: 3}))
    centro = _entrega(hoja, "Centro")
    _entregar(r, centro["id"], {pan: 6}, [{"metodo_pago": "Efectivo", "monto": 603}])
    admin = r["admin"]
    url = f"{ENT}/hojas/{hoja['id']}/rendicion"

    # Cargó 13, entregó 6: vuelven 7 (4 del parcial + 3 de la parada que no se visitó)
    mal = admin.post(url, json={
        "devoluciones": [{"producto_id": pan, "cantidad": 4, "destino": "Reingreso"}], "efectivo_declarado": 1103,
    })
    assert mal.status_code == 422 and _codigo(mal) == "devolucion_no_cuadra"
    assert mal.json()["error"]["details"] == [{"producto_id": pan, "nombre": "Pan", "esperado": 7, "declarado": 4}]
    assert admin.get(f"{ENT}/hojas/{hoja['id']}").json()["estado"] == "En ruta"  # nada se aplicó

    ok = admin.post(url, json={
        "devoluciones": [{"producto_id": pan, "cantidad": 5, "destino": "Reingreso"},
                         {"producto_id": pan, "cantidad": 2, "destino": "Merma"}],
        "efectivo_declarado": 1100,
    })
    assert ok.status_code == 200, ok.text
    h = ok.json()
    assert h["estado"] == "Rendida" and h["rendida_en"]
    assert "diferencia" not in str(h)  # arqueo ciego: la diferencia no viaja en la respuesta
    assert {e["punto_nombre"]: e["estado"] for e in h["entregas"]} == {"Centro": "Parcial", "Norte": "No entregada"}
    assert h["carga"][0] | {} == {"producto_id": pan, "nombre": "Pan", "reservada": 13, "cargada": 13,
                                  "entregada": 6, "devuelta": 7}

    # Pan: 100 − 13 cargados + 5 que reingresan
    assert _producto(admin, pan)["stock_mostrador"] == 92
    with SessionLocal() as s:
        mermas = s.scalars(select(Merma)).all()
        assert [(m.producto_id, m.cantidad_perdida, m.motivo) for m in mermas] == [
            (pan, 2, "Devolución de reparto")
        ]
        turno = s.get(Turno, h["turno_id"])
        assert turno.estado.value == "Cerrado"
    arqueo = admin.get(f"{API}/arqueos").json()[0]
    assert (arqueo["monto_sistema"], arqueo["monto_declarado"], arqueo["diferencia"]) == (1103, 1100, -3)

    # Hoja rendida: ya no se opera
    assert admin.post(url, json={"devoluciones": [], "efectivo_declarado": 0}).status_code == 409
    resp = _entregar(r, centro["id"], {pan: 1})
    assert resp.status_code == 409 and _codigo(resp) == "hoja_cerrada"
    assert r["repa"].post(f"{ENT}/hojas/{hoja['id']}/inicio-ruta", json=op(ubicacion_concedida=True)).status_code == 409


def test_el_reingreso_va_a_la_variante_del_dia_anterior(reparto):
    r, pan = reparto, reparto["pan"]
    admin = r["admin"]
    variante = admin.post(f"{API}/productos", json={"nombre": "Pan del día anterior", "precio_venta": 50,
                                                  "producto_base_id": pan}).json()["id"]
    hoja = _en_ruta(r, (r["centro"], {pan: 10}))
    resp = admin.post(f"{ENT}/hojas/{hoja['id']}/rendicion", json={
        "devoluciones": [{"producto_id": pan, "cantidad": 10, "destino": "Reingreso"}], "efectivo_declarado": 500,
    })
    assert resp.status_code == 200, resp.text
    assert _producto(admin, pan)["stock_mostrador"] == 90          # salió y no vuelve como pan fresco
    assert _producto(admin, variante)["stock_mostrador"] == 10     # vuelve como pan del día anterior


def test_rendir_una_hoja_cargada_que_no_salio(reparto):
    r, pan = reparto, reparto["pan"]
    hoja = _hoja(r, (r["centro"], {pan: 4}))
    _confirmar(r, hoja["id"])
    admin = r["admin"]
    url = f"{ENT}/hojas/{hoja['id']}/rendicion"
    assert admin.post(url, json={"devoluciones": [], "efectivo_declarado": 0}).status_code == 409  # sin cargar
    _cargar(r, hoja["id"])
    ok = admin.post(url, json={
        "devoluciones": [{"producto_id": pan, "cantidad": 4, "destino": "Reingreso"}], "efectivo_declarado": 500,
    })
    assert ok.status_code == 200 and ok.json()["estado"] == "Rendida"
    assert [e["estado"] for e in ok.json()["entregas"]] == ["No entregada"]
    assert _producto(admin, pan)["stock_mostrador"] == 100


def test_un_turno_de_reparto_no_se_cierra_por_la_via_comun(reparto):
    r, pan = reparto, reparto["pan"]
    hoja = _en_ruta(r, (r["centro"], {pan: 1}))
    resp = r["admin"].post(f"{API}/turnos/{hoja['turno_id']}/cierre", json={"monto_declarado": 0})
    assert resp.status_code == 409 and _codigo(resp) == "turno_de_reparto"
    # Y el repartidor no tiene acceso a la caja: no cierra turnos por su cuenta
    assert r["repa"].post(f"{API}/turnos/actual/cierre", json={"monto_declarado": 0}).status_code == 403


# ---------- Armado de hojas ----------


def test_editar_solo_un_borrador(reparto):
    r, pan, medialuna = reparto, reparto["pan"], reparto["medialuna"]
    admin = r["admin"]
    hoja = _hoja(r, (r["centro"], {pan: 4}))
    nueva = admin.patch(f"{ENT}/hojas/{hoja['id']}", json={"paradas": [
        {"punto_entrega_id": r["norte"]["id"], "items": [{"producto_id": medialuna, "cantidad": 7}]},
    ]})
    assert nueva.status_code == 200, nueva.text
    assert [e["punto_nombre"] for e in nueva.json()["entregas"]] == ["Norte"]
    assert nueva.json()["total_planificado"] == 560

    _confirmar(r, hoja["id"])
    assert admin.patch(f"{ENT}/hojas/{hoja['id']}", json={"fecha": "2030-01-01"}).status_code == 409
    admin.post(f"{ENT}/hojas/{hoja['id']}/reapertura")
    assert admin.patch(f"{ENT}/hojas/{hoja['id']}", json={"fecha": "2030-01-01"}).json()["fecha"] == "2030-01-01"


def test_validaciones_de_la_hoja(reparto, como):
    r, pan = reparto, reparto["pan"]
    admin = r["admin"]
    base = {"fecha": stock.hoy_local().isoformat(), "repartidor_id": r["repartidor_id"]}
    items = [{"producto_id": pan, "cantidad": 1}]
    parada = {"punto_entrega_id": r["centro"]["id"], "items": items}

    assert admin.post(f"{ENT}/hojas", json={**base, "paradas": []}).status_code == 422
    repetido = admin.post(f"{ENT}/hojas", json={**base, "paradas": [parada, parada]})
    assert repetido.status_code == 422 and _codigo(repetido) == "punto_repetido"
    assert admin.post(f"{ENT}/hojas", json={**base, "paradas": [{**parada, "punto_entrega_id": 999}]}).status_code == 404
    assert admin.post(f"{ENT}/hojas", json={**base, "paradas": [
        {**parada, "items": [{"producto_id": 999, "cantidad": 1}]}]}).status_code == 404
    como(RolEnum.VENDEDORA, "mostrador")
    uid = next(u for u in admin.get(f"{API}/usuarios").json() if u["username"] == "mostrador")["id"]
    no_repa = admin.post(f"{ENT}/hojas", json={**base, "repartidor_id": uid, "paradas": [parada]})
    assert no_repa.status_code == 422 and _codigo(no_repa) == "repartidor_invalido"
    # Productos repetidos en una parada se suman
    hoja = admin.post(f"{ENT}/hojas", json={**base, "paradas": [{**parada, "items": items + items}]}).json()
    assert hoja["entregas"][0]["items"][0]["cantidad_planificada"] == 2
    # Un punto o producto dado de baja no se puede incluir
    admin.patch(f"{CC}/puntos-entrega/{r['norte']['id']}", json={"activo": False})
    baja = admin.post(f"{ENT}/hojas", json={**base, "paradas": [{**parada, "punto_entrega_id": r["norte"]["id"]}]})
    assert baja.status_code == 409


def test_la_ruta_sugerida_se_calcula_y_se_puede_recalcular(reparto):
    r, pan = reparto, reparto["pan"]
    lejos = r["punto"]("Lejos", ("-34.700000", "-58.500000"), ventana_desde="06:00", ventana_hasta="08:00")
    sin_ubicacion = r["admin"].post(f"{CC}/puntos-entrega", json={"cliente_id": r["cliente"]["id"], "nombre": "Sin GPS"}).json()
    hoja = _hoja(r, (r["centro"], {pan: 1}), (sin_ubicacion, {pan: 1}), (lejos, {pan: 1}), (r["norte"], {pan: 1}))
    orden = [e["punto_nombre"] for e in hoja["entregas"]]
    assert orden[0] == "Lejos"                # cierra antes: se visita primero
    assert orden[-1] == "Sin GPS"             # sin ubicación: al final
    assert hoja["distancia_sugerida_km"] > 0
    again = r["admin"].post(f"{ENT}/hojas/{hoja['id']}/ruta-sugerida")
    assert again.status_code == 200
    assert [e["punto_nombre"] for e in again.json()["entregas"]] == orden


def test_generacion_desde_plantillas(reparto):
    r, pan, medialuna = reparto, reparto["pan"], reparto["medialuna"]
    admin = r["admin"]
    hoy = stock.hoy_local()
    huerfano = r["punto"]("Sin repartidor", ("-34.61", "-58.40"))
    for p in (r["centro"], r["norte"], huerfano):
        admin.put(f"{CC}/puntos-entrega/{p['id']}/plantillas", json={"dias": [
            {"dia_semana": hoy.weekday(), "items": [{"producto_id": pan, "cantidad": 6},
                                                    {"producto_id": medialuna, "cantidad": 2}]},
        ]})
    for p in (r["centro"], r["norte"]):
        admin.patch(f"{CC}/puntos-entrega/{p['id']}", json={"repartidor_habitual_id": r["repartidor_id"]})

    resp = admin.post(f"{ENT}/hojas/generacion", params={"fecha": hoy.isoformat()})
    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()
    assert len(cuerpo["hojas"]) == 1
    assert (cuerpo["hojas"][0]["paradas"], cuerpo["hojas"][0]["estado"]) == (2, "Borrador")
    assert cuerpo["hojas"][0]["total_planificado"] == 2 * (6 * 100.5 + 2 * 80)
    assert cuerpo["omitidos"] == [{"punto": "Sin repartidor", "motivo": "No tiene repartidor habitual."}]

    # Generar de nuevo no duplica nada
    otra = admin.post(f"{ENT}/hojas/generacion", params={"fecha": hoy.isoformat()}).json()
    assert otra["hojas"] == [] and len(otra["omitidos"]) == 3
    assert len(admin.get(f"{ENT}/hojas", params={"fecha": hoy.isoformat()}).json()) == 1
    # Un día sin plantillas no genera nada
    vacio = admin.post(f"{ENT}/hojas/generacion", params={"fecha": (hoy + timedelta(days=1)).isoformat()}).json()
    assert vacio == {"hojas": [], "omitidos": []}


def test_hoja_de_hoy_y_resumen(reparto):
    r, pan, medialuna = reparto, reparto["pan"], reparto["medialuna"]
    assert r["repa"].get(f"{ENT}/hojas/hoy").status_code == 404
    hoja = _en_ruta(r, (r["centro"], {pan: 5}), (r["norte"], {medialuna: 4}))
    hoy = r["repa"].get(f"{ENT}/hojas/hoy")
    assert hoy.status_code == 200 and hoy.json()["id"] == hoja["id"] and len(hoy.json()["entregas"]) == 2
    centro = _entrega(hoy.json(), "Centro")
    _entregar(r, centro["id"], {pan: 5}, [{"metodo_pago": "Efectivo", "monto": 500}])

    resumen = r["admin"].get(f"{ENT}/resumen").json()
    assert resumen == {
        "fecha": stock.hoy_local().isoformat(), "hojas": 1, "paradas": 2, "completadas": 1, "parciales": 0,
        "no_entregadas": 0, "pendientes": 1, "facturacion_reparto": 502.5, "cobrado": 500, "a_cuenta_corriente": 2.5,
    }
    lista = r["admin"].get(f"{ENT}/hojas").json()
    assert [(h["paradas"], h["entregadas"], h["pendientes"]) for h in lista] == [(2, 1, 1)]


# ---------- Permisos ----------


def test_permisos_por_rol(reparto, como):
    r, pan = reparto, reparto["pan"]
    hoja = _en_ruta(r, (r["centro"], {pan: 5}))
    e = hoja["entregas"][0]
    cajera, panadero = como(RolEnum.VENDEDORA), como(RolEnum.PANADERO)
    repa, admin = r["repa"], r["admin"]

    for c in (cajera, panadero, repa):
        assert c.get(f"{ENT}/hojas").status_code == 403
        assert c.post(f"{ENT}/hojas/{hoja['id']}/anulacion").status_code == 403
    assert cajera.get(f"{ENT}/hojas/hoy").status_code == 403
    for c in (cajera, panadero, admin):
        assert c.post(f"{ENT}/{e['id']}/check-in", json=op()).status_code == 403
        assert c.post(f"{ENT}/hojas/{hoja['id']}/recorrido", json={"lote_id": str(uuid.uuid4()),
                                                                    "puntos": [pos()]}).status_code == 403
    assert repa.get(f"{ENT}/hojas/{hoja['id']}/recorrido").status_code == 403
    assert repa.post(f"{ENT}/hojas/{hoja['id']}/rendicion", json={"devoluciones": [], "efectivo_declarado": 0}
                     ).status_code == 403

    # Otro repartidor no toca entregas ajenas
    crear_usuario("repa2", RolEnum.REPARTIDOR)
    otro = login("repa2")
    assert otro.post(f"{ENT}/{e['id']}/check-in", json=op()).status_code == 403
    assert otro.post(f"{ENT}/{e['id']}/confirmacion", json=_confirmacion({pan: 5})).status_code == 403
    assert otro.post(f"{ENT}/{e['id']}/no-entregada", json=op(motivo="x")).status_code == 403
    assert otro.post(f"{ENT}/hojas/{hoja['id']}/recorrido", json={"lote_id": str(uuid.uuid4()),
                                                                   "puntos": [pos()]}).status_code == 403
    assert otro.get(f"{ENT}/hojas/hoy").status_code == 404

    # El repartidor no ve el resto del sistema: pedidos, mermas, recetas ni insumos
    assert repa.get(f"{API}/pedidos").status_code == 403
    assert repa.post(f"{API}/mermas", json={"producto_id": pan, "cantidad_perdida": 1, "motivo": "x"}).status_code == 403
    assert repa.get(f"{API}/materias-primas").status_code == 403
    assert repa.get(f"{API}/productos/{pan}/receta").status_code == 403
    assert repa.post(f"{API}/ventas", json={"items": [{"producto_id": pan, "cantidad": 1}]}).status_code == 403
    assert repa.get(f"{API}/auth/me").status_code == 200


# ---------- Recorrido GPS ----------


def _lote(*puntos, **extra):
    # Un punto por minuto: dos puntos con el mismo instante del dispositivo son el mismo punto
    return {
        "lote_id": str(uuid.uuid4()),
        "puntos": [{**pos(c), "registrado_en": ahora(minutes=len(puntos) - i)} for i, c in enumerate(puntos)],
        **extra,
    }


def test_un_lote_gps_repetido_no_duplica(reparto):
    r, pan = reparto, reparto["pan"]
    hoja = _hoja(r, (r["centro"], {pan: 1}))
    _confirmar(r, hoja["id"])
    _cargar(r, hoja["id"])
    url = f"{ENT}/hojas/{hoja['id']}/recorrido"
    lote = _lote(CENTRO)
    assert r["repa"].post(url, json=lote).status_code == 409  # todavía no salió a la ruta

    _salir(r, hoja["id"])
    lote = {"lote_id": str(uuid.uuid4()), "puntos": [
        {**pos(CENTRO), "registrado_en": ahora(minutes=3)},
        {**pos(("-34.600000", "-58.390000")), "registrado_en": ahora(minutes=2)},
        {**pos(("-34.590000", "-58.400000")), "registrado_en": ahora(minutes=1)},
    ]}
    primera = r["repa"].post(url, json=lote)
    assert primera.status_code == 200 and primera.json() == {"recibidos": 3, "nuevos": 3, "eventos_nuevos": 0}
    segunda = r["repa"].post(url, json=lote)
    assert segunda.json() == {"recibidos": 3, "nuevos": 0, "eventos_nuevos": 0}
    with SessionLocal() as s:
        assert s.scalar(select(func.count()).select_from(RecorridoPunto)) == 4  # 3 + el punto de salida
    # Una sincronización parcial (reenvío con un punto nuevo) solo suma lo nuevo
    mas = {**lote, "puntos": [*lote["puntos"], {**pos(NORTE), "registrado_en": ahora()}]}
    assert r["repa"].post(url, json=mas).json()["nuevos"] == 1


def test_validaciones_del_lote_gps(reparto):
    r, pan = reparto, reparto["pan"]
    hoja = _en_ruta(r, (r["centro"], {pan: 1}))
    url = f"{ENT}/hojas/{hoja['id']}/recorrido"
    c = r["repa"]
    assert c.post(url, json={"lote_id": str(uuid.uuid4()), "puntos": []}).status_code == 422
    assert c.post(url, json={"lote_id": str(uuid.uuid4()), "puntos": [pos(("95", "10"))]}).status_code == 422
    viejo = {**pos(), "registrado_en": ahora(days=400)}
    assert c.post(url, json={"lote_id": str(uuid.uuid4()), "puntos": [viejo]}).status_code == 422  # reloj desfasado
    futuro = {**pos(), "registrado_en": (datetime.now(UTC) + timedelta(days=5)).isoformat()}
    assert c.post(url, json={"lote_id": str(uuid.uuid4()), "puntos": [futuro]}).status_code == 422
    # Un GPS real entrega muchos decimales: se redondean en lugar de rechazar el lote
    preciso = pos(("-34.603722123456789", "-58.381592987654321"), precision_m="4.123456")
    ok = c.post(url, json={"lote_id": str(uuid.uuid4()), "puntos": [preciso]})
    assert ok.status_code == 200, ok.text
    with SessionLocal() as s:
        punto = s.scalars(select(RecorridoPunto).order_by(RecorridoPunto.recibido_en_servidor.desc())).first()
        assert (punto.latitud, punto.longitud) == (Decimal("-34.603722"), Decimal("-58.381593"))


def test_el_mapa_compara_ruta_sugerida_con_la_real(reparto):
    r, pan, medialuna = reparto, reparto["pan"], reparto["medialuna"]
    hoja = _en_ruta(r, (r["centro"], {pan: 2}), (r["norte"], {medialuna: 2}))
    url = f"{ENT}/hojas/{hoja['id']}/recorrido"
    # Traza: sale del centro, pasa por varios puntos alineados y llega al norte
    recta = [(f"{-34.6037 + i * 0.002:.6f}", "-58.381600") for i in range(12)]
    puntos = [{**pos(c), "registrado_en": ahora(minutes=30 - i)} for i, c in enumerate(recta)]
    assert r["repa"].post(url, json={"lote_id": str(uuid.uuid4()), "puntos": puntos}).status_code == 200
    corte = {"lote_id": str(uuid.uuid4()), "eventos": [
        {"tipo": "GPS sin señal", "desde": ahora(minutes=12), "hasta": ahora(minutes=8)},
    ]}
    assert r["repa"].post(url, json=corte).json()["eventos_nuevos"] == 1

    # Centro: confirmada en el lugar; Norte: confirmada a ~5 km de donde está el punto
    centro, norte = _entrega(hoja, "Centro"), _entrega(hoja, "Norte")
    assert _entregar(r, centro["id"], {pan: 2}, posicion=pos(CENTRO)).status_code == 200
    lejos = pos(("-34.625000", "-58.381600"))
    assert _entregar(r, norte["id"], {medialuna: 2}, posicion=lejos).status_code == 200

    mapa = r["admin"].get(url)
    assert mapa.status_code == 200, mapa.text
    m = mapa.json()
    assert [p["nombre"] for p in m["sugerida"]] == [e["punto_nombre"] for e in hoja["entregas"]]
    assert m["puntos_totales"] == 13  # 12 + el de salida
    assert 2 <= len(m["traza"]) < 13  # la traza recta se simplifica
    assert m["traza"][0]["registrado_en"] <= m["traza"][-1]["registrado_en"]
    assert [e["tipo"] for e in m["eventos"]] == ["GPS sin señal"]
    por_nombre = {e["punto_nombre"]: e for e in m["entregas"]}
    assert por_nombre["Centro"]["lejos"] is False and por_nombre["Centro"]["distancia_al_punto_m"] < 50
    assert por_nombre["Norte"]["lejos"] is True and por_nombre["Norte"]["distancia_al_punto_m"] > 4000
    ind = m["indicadores"]
    assert ind["entregas_lejos"] == 1 and ind["tramos_sin_traza"] == 1
    assert ind["distancia_real_km"] > 2 and ind["distancia_sugerida_km"] > 0
    assert m["entregas"][0]["estado"] == "Entregada" and m["estado"] == "En ruta"


def test_la_distancia_real_queda_en_el_resumen_de_la_hoja(reparto):
    r, pan = reparto, reparto["pan"]
    hoja = _en_ruta(r, (r["centro"], {pan: 2}))
    url = f"{ENT}/hojas/{hoja['id']}/recorrido"
    puntos = [{**pos(("-34.600000", "-58.380000")), "registrado_en": ahora(minutes=20)},
              {**pos(("-34.610000", "-58.380000")), "registrado_en": ahora(minutes=10)}]
    r["repa"].post(url, json={"lote_id": str(uuid.uuid4()), "puntos": puntos})
    rend = r["admin"].post(f"{ENT}/hojas/{hoja['id']}/rendicion", json={
        "devoluciones": [{"producto_id": pan, "cantidad": 2, "destino": "Reingreso"}], "efectivo_declarado": 500,
    })
    assert rend.status_code == 200
    # El punto de salida (centro) + 2 puntos sobre el meridiano: ~1,1 km o más
    assert rend.json()["distancia_real_km"] > 1

    # Un lote que llega tarde (sincronización diferida) se guarda y actualiza la distancia
    antes = rend.json()["distancia_real_km"]
    tarde = {**pos(("-34.700000", "-58.380000")), "registrado_en": ahora(minutes=5)}
    assert r["repa"].post(url, json={"lote_id": str(uuid.uuid4()), "puntos": [tarde]}).status_code == 200
    despues = r["admin"].get(f"{ENT}/hojas/{hoja['id']}").json()["distancia_real_km"]
    assert despues > antes


def test_el_resumen_permanece_aunque_se_borre_la_traza(reparto):
    """Lo que se conserva de forma permanente (posición y orden de cada entrega, distancia real)
    no depende de los puntos crudos, que se eliminan a los 90 días."""
    r, pan = reparto, reparto["pan"]
    hoja = _en_ruta(r, (r["centro"], {pan: 2}))
    r["repa"].post(f"{ENT}/hojas/{hoja['id']}/recorrido", json=_lote(CENTRO, NORTE))
    _entregar(r, hoja["entregas"][0]["id"], {pan: 2})
    r["admin"].post(f"{ENT}/hojas/{hoja['id']}/rendicion", json={"devoluciones": [], "efectivo_declarado": 500})
    with SessionLocal() as s:
        from sqlalchemy import delete

        s.execute(delete(RecorridoPunto))
        s.commit()
    h = r["admin"].get(f"{ENT}/hojas/{hoja['id']}").json()
    assert h["distancia_real_km"] > 0
    e = h["entregas"][0]
    assert e["orden_real"] == 1 and e["estado"] == "Entregada"
    with SessionLocal() as s:
        entrega = s.get(Entrega, e["id"])
        assert entrega.latitud is not None and entrega.confirmada_en_dispositivo is not None


# ---------- Tablero y cobro de deuda en la calle ----------


def test_el_tablero_separa_las_ventas_por_canal(reparto, como):
    r, pan = reparto, reparto["pan"]
    hoja = _en_ruta(r, (r["centro"], {pan: 5}))
    _entregar(r, hoja["entregas"][0]["id"], {pan: 5}, [{"metodo_pago": "Efectivo", "monto": 502.5}])
    caja = _abrir_caja(como)
    assert caja.post(f"{API}/ventas", json={"items": [{"producto_id": pan, "cantidad": 1}]}).status_code == 201

    hoy = stock.hoy_local().isoformat()
    resumen = r["admin"].get(f"{API}/finanzas/resumen", params={"desde": hoy, "hasta": hoy}).json()
    canales = {c["canal"]: (c["total"], c["cantidad"]) for c in resumen["ventas_por_canal"]}
    assert canales == {"Reparto": (502.5, 1), "Mostrador": (100.5, 1)}
    assert resumen["ventas_totales"] == 603


def test_el_repartidor_cobra_deuda_en_efectivo_al_turno_de_reparto(reparto):
    r, pan = reparto, reparto["pan"]
    admin = r["admin"]
    otro = admin.post(f"{API}/clientes", json={"nombre": "Otro cliente"}).json()
    # Deuda previa del cliente del punto
    assert admin.post(f"{CC}/clientes/{r['cliente']['id']}/ajustes",
                      json={"importe": 1000, "observacion": "Saldo inicial"}).status_code == 201
    pago = {"monto": 400, "metodo_pago": "Efectivo", "operacion_id": str(uuid.uuid4())}

    # Sin hoja en curso no cobra en la calle
    sin_hoja = r["repa"].post(f"{CC}/clientes/{r['cliente']['id']}/pagos", json=pago)
    assert sin_hoja.status_code == 403

    hoja = _en_ruta(r, (r["centro"], {pan: 1}), fondo=100)
    ok = r["repa"].post(f"{CC}/clientes/{r['cliente']['id']}/pagos", json=pago)
    assert ok.status_code == 201, ok.text
    assert ok.json()["turno_id"] == hoja["turno_id"]
    # Un reintento con la misma operación no cobra dos veces
    assert r["repa"].post(f"{CC}/clientes/{r['cliente']['id']}/pagos", json=pago).status_code == 201
    assert admin.get(f"{CC}/clientes/{r['cliente']['id']}/cuenta-corriente").json()["saldo"] == 600
    # Solo a clientes que están en su hoja
    ajeno = r["repa"].post(f"{CC}/clientes/{otro['id']}/pagos", json={**pago, "operacion_id": str(uuid.uuid4())})
    assert ajeno.status_code == 403
    # No accede a lo demás de la cuenta corriente
    assert r["repa"].get(f"{CC}/saldos").status_code == 403
    assert r["repa"].post(f"{CC}/clientes/{r['cliente']['id']}/ajustes", json={"importe": -600}).status_code == 403

    # El efectivo cobrado cuenta en el arqueo del reparto: fondo 100 + 400
    rend = admin.post(f"{ENT}/hojas/{hoja['id']}/rendicion", json={
        "devoluciones": [{"producto_id": pan, "cantidad": 1, "destino": "Reingreso"}], "efectivo_declarado": 500,
    })
    assert rend.status_code == 200, rend.text
    arqueo = admin.get(f"{API}/arqueos").json()[0]
    assert (arqueo["cobros_efectivo"], arqueo["monto_sistema"], arqueo["diferencia"]) == (400, 500, 0)
