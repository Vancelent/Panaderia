"""Pagos múltiples (ventas_pagos), medios habilitados, cuenta corriente en caja y arqueo."""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.errors import ConflictError
from app.models import (
    EstadoTurnoEnum,
    MetodoPagoEnum,
    RolEnum,
    Turno,
    Usuario,
    Venta,
)
from app.services import caja

API = "/api/v1"


def _abrir(c, monto=1000):
    r = c.post(f"{API}/turnos", json={"efectivo_inicial": monto})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _vender(c, catalogo, *, cantidad=2, **extra):
    body = {"items": [{"producto_id": catalogo["pan"], "cantidad": cantidad}], **extra}
    return c.post(f"{API}/ventas", json=body)


def _stock(c, producto_id):
    return next(p for p in c.get(f"{API}/productos").json() if p["id"] == producto_id)["stock_mostrador"]


# ---------- Un medio y pago mixto ----------


def test_venta_con_un_solo_medio_crea_un_pago(como, catalogo):
    c = como(RolEnum.VENDEDORA)
    _abrir(c)
    r = _vender(c, catalogo, metodo_pago="Tarjeta")
    assert r.status_code == 201, r.text
    venta = r.json()
    assert venta["metodo_pago"] == "Tarjeta"
    assert venta["pagos"] == [
        {"metodo_pago": "Tarjeta", "monto": 201.0, "referencia": None, "estado": "Aprobado"}
    ]


def test_pago_mixto_registra_cada_medio_y_el_principal_es_el_mayor(como, catalogo):
    c = como(RolEnum.VENDEDORA)
    _abrir(c)
    r = _vender(c, catalogo, pagos=[
        {"metodo_pago": "Efectivo", "monto": 100},
        {"metodo_pago": "Transferencia", "monto": 101, "referencia": "OP-778"},
    ])
    assert r.status_code == 201, r.text
    venta = r.json()
    assert venta["monto"] == 201.0
    assert venta["metodo_pago"] == "Transferencia"  # el de mayor monto
    assert [(p["metodo_pago"], p["monto"], p["referencia"]) for p in venta["pagos"]] == [
        ("Efectivo", 100.0, None),
        ("Transferencia", 101.0, "OP-778"),
    ]
    assert _stock(c, catalogo["pan"]) == 8


# ---------- pagos_no_cuadran ----------


@pytest.mark.parametrize(
    "pagos,pagado",
    [
        ([{"metodo_pago": "Efectivo", "monto": 200}], 200.0),                       # falta 1
        ([{"metodo_pago": "Efectivo", "monto": 150},
          {"metodo_pago": "Tarjeta", "monto": 60}], 210.0),                         # sobran 9
        ([{"metodo_pago": "Efectivo", "monto": 100},
          {"metodo_pago": "Tarjeta", "monto": 100.99}], 200.99),                    # falta 1 centavo
    ],
)
def test_pagos_que_no_suman_el_total_se_rechazan(como, catalogo, pagos, pagado):
    c = como(RolEnum.VENDEDORA)
    _abrir(c)
    r = _vender(c, catalogo, pagos=pagos)
    assert r.status_code == 422
    error = r.json()["error"]
    assert error["code"] == "pagos_no_cuadran"
    assert error["details"] == {"total": 201.0, "pagado": pagado}


def test_pagos_no_cuadran_no_deja_rastros(como, catalogo):
    """Rechazar la venta no descuenta stock, no crea venta ni movimientos."""
    c = como(RolEnum.VENDEDORA)
    _abrir(c)
    r = _vender(c, catalogo, pagos=[{"metodo_pago": "Efectivo", "monto": 1}])
    assert r.status_code == 422
    assert _stock(c, catalogo["pan"]) == 10
    assert c.get(f"{API}/turnos/actual/ventas").json() == []


def test_el_total_lo_decide_el_servidor_no_el_cliente(como, catalogo):
    """Mandar pagos por un total inventado no sirve: el servidor recalcula con los precios."""
    c = como(RolEnum.VENDEDORA)
    _abrir(c)
    r = _vender(c, catalogo, total=1, pagos=[{"metodo_pago": "Efectivo", "monto": 1}])
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "pagos_no_cuadran"


def test_centavos_exactos_con_decimal(como, catalogo):
    c = como(RolEnum.VENDEDORA)
    _abrir(c)
    # 1 pan = 100.50: 100.00 + 0.50 cuadra; 100.00 + 0.40 no
    ok = _vender(c, catalogo, cantidad=1, pagos=[
        {"metodo_pago": "Efectivo", "monto": "100.00"}, {"metodo_pago": "Tarjeta", "monto": "0.50"}])
    assert ok.status_code == 201, ok.text
    mal = _vender(c, catalogo, cantidad=1, pagos=[
        {"metodo_pago": "Efectivo", "monto": "100.00"}, {"metodo_pago": "Tarjeta", "monto": "0.40"}])
    assert mal.status_code == 422
    assert mal.json()["error"]["code"] == "pagos_no_cuadran"


@pytest.mark.parametrize("monto", [0, -5, "abc"])
def test_monto_de_pago_invalido(como, catalogo, monto):
    c = como(RolEnum.VENDEDORA)
    _abrir(c)
    r = _vender(c, catalogo, pagos=[{"metodo_pago": "Efectivo", "monto": monto}])
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_demasiados_pagos(como, catalogo):
    c = como(RolEnum.VENDEDORA)
    _abrir(c)
    pagos = [{"metodo_pago": "Efectivo", "monto": 1} for _ in range(6)]
    assert _vender(c, catalogo, pagos=pagos).status_code == 422


# ---------- Medios habilitados ----------


def test_medios_de_pago_por_defecto(como):
    c = como(RolEnum.VENDEDORA)
    r = c.get(f"{API}/medios-pago")
    assert r.status_code == 200
    assert r.json() == {"habilitados": ["Efectivo", "Transferencia", "Tarjeta"], "cuenta_corriente": True}


def test_qr_no_habilitado_se_rechaza_y_se_habilita_por_configuracion(como, catalogo, monkeypatch):
    c = como(RolEnum.VENDEDORA)
    _abrir(c)
    r = _vender(c, catalogo, metodo_pago="QR")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "medio_pago_no_habilitado"

    monkeypatch.setattr(
        get_settings(), "medios_pago_habilitados", [MetodoPagoEnum.EFECTIVO, MetodoPagoEnum.QR]
    )
    assert c.get(f"{API}/medios-pago").json()["habilitados"] == ["Efectivo", "QR"]
    ok = _vender(c, catalogo, pagos=[{"metodo_pago": "QR", "monto": 201, "referencia": "qr-1"}])
    assert ok.status_code == 201, ok.text
    assert ok.json()["pagos"][0]["metodo_pago"] == "QR"


# ---------- Cuenta corriente desde la caja ----------


def test_cuenta_corriente_requiere_cliente(como, catalogo):
    c = como(RolEnum.VENDEDORA)
    _abrir(c)
    r = _vender(c, catalogo, metodo_pago="Cuenta corriente")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "cliente_requerido"
    assert _stock(c, catalogo["pan"]) == 10


def test_venta_parte_en_efectivo_parte_a_cuenta_corriente(como, catalogo):
    vendedora = como(RolEnum.VENDEDORA)
    admin = como(RolEnum.ADMIN)
    cliente = vendedora.post(f"{API}/clientes", json={"nombre": "Bar del Sur"}).json()
    _abrir(vendedora)

    r = _vender(vendedora, catalogo, cliente_id=cliente["id"], pagos=[
        {"metodo_pago": "Efectivo", "monto": 100},
        {"metodo_pago": "Cuenta corriente", "monto": 101},
    ])
    assert r.status_code == 201, r.text
    assert r.json()["metodo_pago"] == "Cuenta corriente"

    cuenta = admin.get(f"{API}/contabilidad/clientes/{cliente['id']}/cuenta-corriente").json()
    assert cuenta["saldo"] == 101.0
    assert len(cuenta["movimientos"]) == 1
    cargo = cuenta["movimientos"][0]
    assert (cargo["tipo"], cargo["importe"], cargo["venta_id"]) == ("Cargo", 101.0, r.json()["id"])
    assert vendedora.get(f"{API}/clientes/{cliente['id']}").json()["saldo_cuenta_corriente"] == 101.0


def test_venta_rechazada_no_deja_cargo_en_la_cuenta(como, catalogo):
    vendedora = como(RolEnum.VENDEDORA)
    admin = como(RolEnum.ADMIN)
    cliente = vendedora.post(f"{API}/clientes", json={"nombre": "Bar del Sur"}).json()
    _abrir(vendedora)
    r = _vender(vendedora, catalogo, cantidad=99, cliente_id=cliente["id"],
                metodo_pago="Cuenta corriente")
    assert r.status_code == 409
    cuenta = admin.get(f"{API}/contabilidad/clientes/{cliente['id']}/cuenta-corriente").json()
    assert cuenta["saldo"] == 0 and cuenta["movimientos"] == []


# ---------- Arqueo ----------


def test_arqueo_con_pago_mixto_solo_cuenta_la_parte_en_efectivo(como, catalogo):
    vendedora = como(RolEnum.VENDEDORA)
    admin = como(RolEnum.ADMIN)
    _abrir(vendedora, 1000)
    _vender(vendedora, catalogo, pagos=[
        {"metodo_pago": "Efectivo", "monto": 100},
        {"metodo_pago": "Transferencia", "monto": 101},
    ])
    # El cajero cuenta 1100 en el cajón: fondo 1000 + 100 en efectivo
    assert vendedora.post(f"{API}/turnos/actual/cierre", json={"monto_declarado": 1100}).status_code == 200

    arqueo = admin.get(f"{API}/arqueos").json()[0]
    assert arqueo["ventas_efectivo"] == 100.0
    assert arqueo["ventas_otros_medios"] == 101.0
    assert arqueo["monto_sistema"] == 1100.0
    assert arqueo["diferencia"] == 0.0


def test_arqueo_suma_los_cobros_de_cuenta_corriente_en_efectivo(como):
    encargada = como(RolEnum.ENCARGADA)
    cliente = encargada.post(f"{API}/clientes", json={"nombre": "Kiosco Norte"}).json()
    encargada.post(f"{API}/contabilidad/clientes/{cliente['id']}/ajustes",
                   json={"importe": 200, "observacion": "Deuda inicial"})
    _abrir(encargada, 500)

    r = encargada.post(f"{API}/contabilidad/clientes/{cliente['id']}/pagos",
                       json={"monto": 50, "metodo_pago": "Efectivo"})
    assert r.status_code == 201, r.text
    assert r.json()["turno_id"] is not None

    encargada.post(f"{API}/turnos/actual/cierre", json={"monto_declarado": 550})
    arqueo = encargada.get(f"{API}/arqueos").json()[0]
    assert arqueo["cobros_efectivo"] == 50.0
    assert arqueo["monto_sistema"] == 550.0
    assert arqueo["diferencia"] == 0.0


def test_arqueo_de_ventas_viejas_sigue_funcionando(como, catalogo):
    """Sin pagos mixtos, el arqueo es el de siempre."""
    vendedora = como(RolEnum.VENDEDORA)
    admin = como(RolEnum.ADMIN)
    _abrir(vendedora, 1000)
    _vender(vendedora, catalogo, metodo_pago="Efectivo")
    _vender(vendedora, catalogo, metodo_pago="Tarjeta")
    vendedora.post(f"{API}/turnos/actual/cierre", json={"monto_declarado": 1201})
    arqueo = admin.get(f"{API}/arqueos").json()[0]
    assert (arqueo["monto_sistema"], arqueo["ventas_otros_medios"], arqueo["diferencia"]) == (1201.0, 201.0, 0.0)


# ---------- Tablero ----------


def test_resumen_por_medio_reparte_los_pagos_mixtos(como, catalogo):
    vendedora = como(RolEnum.VENDEDORA)
    admin = como(RolEnum.ADMIN)
    _abrir(vendedora)
    _vender(vendedora, catalogo, pagos=[
        {"metodo_pago": "Efectivo", "monto": 100}, {"metodo_pago": "Transferencia", "monto": 101}])
    _vender(vendedora, catalogo, cantidad=1, metodo_pago="Efectivo")

    resumen = admin.get(f"{API}/finanzas/resumen").json()
    por_medio = {m["metodo_pago"]: (m["total"], m["cantidad"]) for m in resumen["ventas_por_medio"]}
    assert por_medio == {"Efectivo": (200.5, 2), "Transferencia": (101.0, 1)}
    assert resumen["ventas_totales"] == 301.5


# ---------- Turno cerrado: el bloqueo relee el estado ----------


def test_venta_con_turno_cerrado_por_otra_transaccion_se_rechaza(como, catalogo, db):
    """El turno puede estar cargado en la sesión como ABIERTO y haberse cerrado después:
    el bloqueo lo vuelve a leer (populate_existing) en lugar de confiar en el objeto viejo."""
    vendedora = como(RolEnum.VENDEDORA, "cajera")
    _abrir(vendedora)
    usuario = db.scalar(select(Usuario).where(Usuario.username == "cajera"))
    turno = caja.turno_abierto(db, usuario)  # en la sesión db, estado ABIERTO
    assert turno.estado == EstadoTurnoEnum.ABIERTO

    vendedora.post(f"{API}/turnos/actual/cierre", json={"monto_declarado": 1000})  # otra sesión
    with pytest.raises(ConflictError) as e:
        caja.crear_venta(db, usuario=usuario, turno=turno, items=[(catalogo["pan"], 1)],
                         metodo_pago=MetodoPagoEnum.EFECTIVO)
    assert e.value.code == "turno_cerrado"
    db.rollback()
    assert db.scalar(select(Venta.id)) is None
    assert db.get(Turno, turno.id).estado == EstadoTurnoEnum.CERRADO


def test_los_importes_de_pago_son_decimal(como, catalogo, db):
    c = como(RolEnum.VENDEDORA)
    _abrir(c)
    _vender(c, catalogo, cantidad=1, metodo_pago="Efectivo")
    from app.models import VentaPago

    pago = db.scalar(select(VentaPago))
    assert isinstance(pago.monto, Decimal) and pago.monto == Decimal("100.50")
