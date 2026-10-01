import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.errors import AppError, ConflictError
from app.db.session import SessionLocal
from app.models import (
    ConversionDiaAnterior,
    DetalleVenta,
    EstadoTurnoEnum,
    MetodoPagoEnum,
    MovimientoCuentaCorriente,
    Producto,
    RolEnum,
    Turno,
    Usuario,
)
from app.schemas.contabilidad import PagoCuentaCorrienteIn
from app.services import caja, contabilidad, stock
from tests.conftest import login

API = "/api/v1"

pytestmark = pytest.mark.skipif(
    not os.environ["DATABASE_URL"].startswith("postgresql"),
    reason="El bloqueo de filas (FOR UPDATE) solo se puede probar en Postgres",
)


def test_ventas_concurrentes_no_sobrevenden(como, catalogo):
    # 3 cajeras con turno abierto compiten por las 5 medialunas
    cajas = []
    for i in range(3):
        como(RolEnum.VENDEDORA, f"caja{i}")
        c = login(f"caja{i}")
        c.post(f"{API}/turnos", json={"efectivo_inicial": 0})
        cajas.append(c)

    def vender(n):
        c = cajas[n % len(cajas)]
        r = c.post(f"{API}/ventas", json={"items": [{"producto_id": catalogo["medialuna"], "cantidad": 1}]})
        return r.status_code

    with ThreadPoolExecutor(max_workers=12) as pool:
        resultados = list(pool.map(vender, range(12)))

    assert resultados.count(201) == 5
    assert resultados.count(409) == 7
    stock = {p["id"]: p["stock_mostrador"] for p in cajas[0].get(f"{API}/productos").json()}
    assert stock[catalogo["medialuna"]] == 0


# ---------- Fase 1: turno, día anterior y cuenta corriente ----------


def _uid(username):
    with SessionLocal() as s:
        return s.scalar(select(Usuario.id).where(Usuario.username == username))


def _con_variante(admin, base_id, nombre):
    r = admin.post(f"{API}/productos", json={"nombre": nombre, "precio_venta": 50, "producto_base_id": base_id})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_el_cierre_de_turno_espera_a_las_ventas_en_curso(como, catalogo):
    """Una venta ya iniciada no puede quedar fuera del arqueo: el cierre (FOR UPDATE) espera
    a que ella (FOR SHARE) termine."""
    admin = como(RolEnum.ADMIN)
    como(RolEnum.VENDEDORA, "cajera")
    turno_id = login("cajera").post(f"{API}/turnos", json={"efectivo_inicial": 1000}).json()["id"]
    uid = _uid("cajera")
    venta_en_curso, soltar, errores = threading.Event(), threading.Event(), []

    def vender():
        try:
            with SessionLocal() as s:
                caja.crear_venta(
                    s, usuario=s.get(Usuario, uid), turno=s.get(Turno, turno_id),
                    items=[(catalogo["pan"], 2)], metodo_pago=MetodoPagoEnum.EFECTIVO, commit=False,
                )
                venta_en_curso.set()  # la venta ya tomó sus bloqueos pero todavía no confirmó
                soltar.wait(20)
                s.commit()
        except Exception as e:  # noqa: BLE001
            errores.append(e)
            venta_en_curso.set()

    def cerrar():
        try:
            with SessionLocal() as s:
                caja.cerrar_turno(s, turno_id, Decimal("1201"))
        except Exception as e:  # noqa: BLE001
            errores.append(e)

    t_venta = threading.Thread(target=vender)
    t_venta.start()
    assert venta_en_curso.wait(20)
    t_cierre = threading.Thread(target=cerrar)
    t_cierre.start()
    time.sleep(1.0)
    assert t_cierre.is_alive(), "el cierre no esperó a la venta en curso"

    soltar.set()
    t_venta.join(20)
    t_cierre.join(20)
    assert not errores, errores

    arqueo = admin.get(f"{API}/arqueos").json()[0]
    assert arqueo["ventas_efectivo"] == 201.0  # la venta entró al arqueo
    assert arqueo["monto_sistema"] == 1201.0 and arqueo["diferencia"] == 0.0


def test_una_venta_que_espera_al_cierre_se_rechaza(como, catalogo):
    """El caso inverso: el cierre llega primero. La venta espera, relee el turno ya
    cerrado y se rechaza en lugar de colarse en un turno que ya tiene arqueo."""
    como(RolEnum.VENDEDORA, "cajera")
    turno_id = login("cajera").post(f"{API}/turnos", json={"efectivo_inicial": 0}).json()["id"]
    uid = _uid("cajera")
    resultado = {}

    def vender():
        with SessionLocal() as s:
            try:
                caja.crear_venta(
                    s, usuario=s.get(Usuario, uid), turno=s.get(Turno, turno_id),
                    items=[(catalogo["pan"], 1)], metodo_pago=MetodoPagoEnum.EFECTIVO,
                )
                resultado["codigo"] = "ok"
            except ConflictError as e:
                resultado["codigo"] = e.code

    with SessionLocal() as cierre:
        turno = cierre.scalar(select(Turno).where(Turno.id == turno_id).with_for_update())
        t = threading.Thread(target=vender)
        t.start()
        time.sleep(1.0)
        assert t.is_alive(), "la venta no esperó al cierre"
        turno.estado = EstadoTurnoEnum.CERRADO
        cierre.commit()
    t.join(20)
    assert resultado["codigo"] == "turno_cerrado"
    with SessionLocal() as s:
        assert s.scalar(select(func.count(DetalleVenta.id))) == 0
        assert s.get(Producto, catalogo["pan"]).stock_mostrador == 10


def test_dia_anterior_concurrente_nunca_pasa_mas_de_lo_disponible(como, catalogo):
    admin = como(RolEnum.ADMIN, "jefa")
    variante = _con_variante(admin, catalogo["pan"], "Pan (día anterior)")
    uid = _uid("jefa")

    def pasar(_):
        with SessionLocal() as s:
            try:
                stock.pasar_a_dia_anterior(s, s.get(Usuario, uid), [(catalogo["pan"], 3)])
                return "ok"
            except ConflictError as e:
                s.rollback()
                return e.code

    with ThreadPoolExecutor(max_workers=8) as pool:
        resultados = list(pool.map(pasar, range(8)))

    assert resultados.count("ok") == 3  # 3 × 3 = 9 de las 10 unidades
    assert resultados.count("stock_insuficiente") == 5
    with SessionLocal() as s:
        assert s.get(Producto, catalogo["pan"]).stock_mostrador == 1
        assert s.get(Producto, variante).stock_mostrador == 9
        assert s.scalar(select(func.sum(ConversionDiaAnterior.cantidad))) == 9


def test_ventas_y_conversiones_cruzadas_no_se_traban_ni_pierden_stock(como, catalogo):
    """Sin deadlocks (todo bloquea por id) y con el stock conservado: lo que se vende más lo que
    queda en el producto y en su variante es siempre lo que había."""
    admin = como(RolEnum.ADMIN, "jefa")
    var_pan = _con_variante(admin, catalogo["pan"], "Pan (día anterior)")
    var_med = _con_variante(admin, catalogo["medialuna"], "Medialuna (día anterior)")
    como(RolEnum.VENDEDORA, "cajera")
    turno_id = login("cajera").post(f"{API}/turnos", json={"efectivo_inicial": 0}).json()["id"]
    uid_caja, uid_jefa = _uid("cajera"), _uid("jefa")
    with SessionLocal() as s:
        s.get(Producto, catalogo["pan"]).stock_mostrador = 200
        s.get(Producto, catalogo["medialuna"]).stock_mostrador = 200
        s.commit()

    def tarea(n):
        pan, med = catalogo["pan"], catalogo["medialuna"]
        with SessionLocal() as s:
            try:
                if n % 3 == 0:  # venta con los productos en un orden
                    caja.crear_venta(s, usuario=s.get(Usuario, uid_caja), turno=s.get(Turno, turno_id),
                                     items=[(pan, 1), (med, 1)], metodo_pago=MetodoPagoEnum.EFECTIVO)
                elif n % 3 == 1:  # venta con el orden inverso
                    caja.crear_venta(s, usuario=s.get(Usuario, uid_caja), turno=s.get(Turno, turno_id),
                                     items=[(med, 1), (pan, 1)], metodo_pago=MetodoPagoEnum.EFECTIVO)
                else:  # conversión de los dos
                    stock.pasar_a_dia_anterior(s, s.get(Usuario, uid_jefa), [(med, 2), (pan, 2)])
                return "ok"
            except AppError as e:
                s.rollback()
                return e.code

    with ThreadPoolExecutor(max_workers=10) as pool:
        resultados = list(pool.map(tarea, range(60)))
    assert set(resultados) == {"ok"}, set(resultados)

    with SessionLocal() as s:
        for base, variante in ((catalogo["pan"], var_pan), (catalogo["medialuna"], var_med)):
            vendidas = s.scalar(
                select(func.coalesce(func.sum(DetalleVenta.cantidad), 0)).where(DetalleVenta.producto_id == base)
            )
            quedan = s.get(Producto, base).stock_mostrador + s.get(Producto, variante).stock_mostrador
            assert vendidas == 40 and quedan + vendidas == 200
            assert s.get(Producto, base).stock_mostrador >= 0


def test_pagos_de_cuenta_corriente_concurrentes_mantienen_el_saldo(como):
    admin = como(RolEnum.ADMIN, "jefa")
    cliente = admin.post(f"{API}/clientes", json={"nombre": "Bar Concurrente"}).json()["id"]
    uid = _uid("jefa")

    def pagar(_):
        with SessionLocal() as s:
            datos = PagoCuentaCorrienteIn(
                monto=Decimal("10"), metodo_pago=MetodoPagoEnum.TRANSFERENCIA, operacion_id=uuid.uuid4()
            )
            contabilidad.registrar_pago(s, s.get(Usuario, uid), cliente, datos)

    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(pagar, range(30)))

    with SessionLocal() as s:
        assert s.scalar(select(func.count(MovimientoCuentaCorriente.id))) == 30
        assert contabilidad.obtener_cuenta(s, cliente).saldo_cuenta_corriente == Decimal("-300.00")
        assert contabilidad.verificar_saldos(s) == []


def test_el_mismo_reintento_simultaneo_se_aplica_una_sola_vez(como):
    admin = como(RolEnum.ADMIN, "jefa")
    cliente = admin.post(f"{API}/clientes", json={"nombre": "Bar Reintento"}).json()["id"]
    uid = _uid("jefa")
    operacion = uuid.uuid4()

    def pagar(_):
        with SessionLocal() as s:
            datos = PagoCuentaCorrienteIn(
                monto=Decimal("25"), metodo_pago=MetodoPagoEnum.TRANSFERENCIA, operacion_id=operacion
            )
            return contabilidad.registrar_pago(s, s.get(Usuario, uid), cliente, datos).id

    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(pagar, range(8)))

    assert len(set(ids)) == 1  # los 8 reintentos devuelven el mismo movimiento
    with SessionLocal() as s:
        assert s.scalar(select(func.count(MovimientoCuentaCorriente.id))) == 1
        assert contabilidad.obtener_cuenta(s, cliente).saldo_cuenta_corriente == Decimal("-25.00")
