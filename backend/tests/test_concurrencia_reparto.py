"""Concurrencia del reparto contra la caja (jerarquía de bloqueos de docs/rfc-001 §3.4).

Solo corren contra PostgreSQL: el bloqueo de filas (FOR UPDATE / FOR SHARE) no existe en SQLite.
"""

import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models import (
    Entrega,
    EstadoTurnoEnum,
    HojaRuta,
    MovimientoCuentaCorriente,
    Producto,
    RolEnum,
    Turno,
    Venta,
)
from app.services import turnos
from tests.conftest import crear_usuario, login
from tests.test_entregas import (
    CENTRO,
    ENT,
    _cargar,
    _codigo,
    _confirmacion,
    _confirmar,
    _en_ruta,
    _entregar,
    _hoja,
)

API = "/api/v1"

pytestmark = pytest.mark.skipif(
    not os.environ["DATABASE_URL"].startswith("postgresql"),
    reason="El bloqueo de filas (FOR UPDATE) solo se puede probar en Postgres",
)


@pytest.mark.parametrize("ronda", range(4))
def test_confirmar_la_hoja_y_vender_a_la_vez_nunca_vende_lo_reservado(reparto, ronda):
    """Quedan 10 panes; la hoja reserva 8 mientras tres cajas venden de a uno. Gane quien gane,
    lo reservado nunca se vende y el stock nunca queda en negativo."""
    r, pan = reparto, reparto["pan"]
    r["admin"].put(f"{API}/productos/{pan}/stock", json={"stock_mostrador": 10})
    hoja = _hoja(r, (r["centro"], {pan: 8}))
    cajas = []
    for i in range(3):
        crear_usuario(f"caja{ronda}{i}", RolEnum.VENDEDORA)
        c = login(f"caja{ronda}{i}")
        assert c.post(f"{API}/turnos", json={"efectivo_inicial": 0}).status_code == 201
        cajas.append(c)

    def accion(n):
        if n == 5:
            return "hoja", _confirmar(r, hoja["id"]).status_code
        c = cajas[n % 3]
        return "venta", c.post(f"{API}/ventas", json={"items": [{"producto_id": pan, "cantidad": 1}]}).status_code

    with ThreadPoolExecutor(max_workers=10) as pool:
        resultados = list(pool.map(accion, range(10)))

    confirmada = ("hoja", 200) in resultados
    ventas_ok = resultados.count(("venta", 201))
    assert set(resultados) <= {("hoja", 200), ("hoja", 409), ("venta", 201), ("venta", 409)}, resultados
    with SessionLocal() as s:
        p = s.get(Producto, pan)
        assert p.stock_mostrador == 10 - ventas_ok
        assert p.stock_reservado == (8 if confirmada else 0)
        assert 0 <= p.stock_reservado <= p.stock_mostrador
    if confirmada:
        assert ventas_ok <= 2, "se vendió mercadería reservada"
    else:
        assert ventas_ok >= 3, "la hoja solo puede fallar si la caja ya había vendido el stock"


def test_dos_hojas_con_los_mismos_productos_en_distinto_orden_no_se_traban(reparto):
    r, pan, medialuna = reparto, reparto["pan"], reparto["medialuna"]
    a = _hoja(r, (r["centro"], {pan: 5, medialuna: 5}))
    b = _hoja(r, (r["norte"], {medialuna: 7, pan: 7}))
    with ThreadPoolExecutor(max_workers=2) as pool:
        estados = list(pool.map(lambda h: _confirmar(r, h["id"]).status_code, [a, b, a, b]))
    assert estados.count(200) == 2 and estados.count(409) == 2  # la segunda vez ya no es borrador
    with SessionLocal() as s:
        assert s.get(Producto, pan).stock_reservado == 12
        assert s.get(Producto, medialuna).stock_reservado == 12


def test_confirmaciones_simultaneas_asignan_orden_y_remito_sin_repetir(reparto):
    r, pan = reparto, reparto["pan"]
    extra = [r["punto"](f"Local {i}", CENTRO) for i in range(2)]
    hoja = _en_ruta(r, (r["centro"], {pan: 3}), (r["norte"], {pan: 3}), *((p, {pan: 3}) for p in extra))
    clientes = [login("repa") for _ in hoja["entregas"]]

    def entregar(i):
        e = hoja["entregas"][i]
        return clientes[i].post(f"{ENT}/{e['id']}/confirmacion", json=_confirmacion({pan: 3}))

    with ThreadPoolExecutor(max_workers=4) as pool:
        respuestas = list(pool.map(entregar, range(4)))
    assert [x.status_code for x in respuestas] == [200] * 4, [x.text for x in respuestas]
    assert sorted(x.json()["orden_real"] for x in respuestas) == [1, 2, 3, 4]
    assert sorted(x.json()["numero_remito"] for x in respuestas) == [1, 2, 3, 4]
    with SessionLocal() as s:
        assert s.scalar(select(func.count()).select_from(Venta)) == 4
        # Todo a cuenta corriente: el saldo es la suma exacta de los cuatro cargos
        saldo = s.scalar(select(func.sum(MovimientoCuentaCorriente.importe)))
        assert saldo == 4 * 3 * 100.5


def test_el_mismo_operacion_id_en_paralelo_se_aplica_una_sola_vez(reparto):
    r, pan = reparto, reparto["pan"]
    hoja = _en_ruta(r, (r["centro"], {pan: 5}))
    e = hoja["entregas"][0]
    cuerpo = _confirmacion({pan: 5}, pagos=[{"metodo_pago": "Efectivo", "monto": 100}])
    clientes = [login("repa") for _ in range(6)]

    with ThreadPoolExecutor(max_workers=6) as pool:
        respuestas = list(pool.map(lambda c: c.post(f"{ENT}/{e['id']}/confirmacion", json=cuerpo), clientes))
    assert [x.status_code for x in respuestas] == [200] * 6, [x.text for x in respuestas]
    assert all(x.json() == respuestas[0].json() for x in respuestas)
    with SessionLocal() as s:
        assert s.scalar(select(func.count()).select_from(Venta)) == 1
        assert s.scalar(select(func.count()).select_from(MovimientoCuentaCorriente)) == 1
        assert s.scalar(select(Entrega.numero_remito)) == 1


def test_la_rendicion_espera_a_las_entregas_en_curso(reparto):
    """Una entrega que ya tomó el turno (FOR SHARE) no puede quedar fuera del arqueo: la rendición
    (FOR UPDATE) espera a que termine."""
    r, pan = reparto, reparto["pan"]
    hoja = _en_ruta(r, (r["centro"], {pan: 5}))
    resultado = {}

    def rendir():
        resultado["resp"] = r["admin"].post(
            f"{ENT}/hojas/{hoja['id']}/rendicion",
            json={"devoluciones": [{"producto_id": pan, "cantidad": 5, "destino": "Reingreso"}],
                  "efectivo_declarado": 500},
        )

    with SessionLocal() as entrega_en_curso:
        turnos.bloquear_para_cobro(entrega_en_curso, hoja["turno_id"])  # lo que hace una entrega en curso
        t = threading.Thread(target=rendir)
        t.start()
        time.sleep(1.0)
        assert t.is_alive(), "la rendición no esperó a la entrega en curso"
        entrega_en_curso.commit()
    t.join(20)
    assert resultado["resp"].status_code == 200, resultado["resp"].text


def test_una_entrega_que_espera_a_la_rendicion_se_rechaza_con_hoja_cerrada(reparto):
    r, pan = reparto, reparto["pan"]
    hoja = _en_ruta(r, (r["centro"], {pan: 5}))
    e = hoja["entregas"][0]
    resultado = {}

    def entregar():
        resultado["resp"] = _entregar(r, e["id"], {pan: 5})

    with SessionLocal() as rendicion:
        rendicion.scalar(select(Turno).where(Turno.id == hoja["turno_id"]).with_for_update())
        t = threading.Thread(target=entregar)
        t.start()
        time.sleep(1.0)
        assert t.is_alive(), "la entrega no esperó a la rendición"
        rendicion.get(Turno, hoja["turno_id"]).estado = EstadoTurnoEnum.CERRADO
        rendicion.commit()
    t.join(20)
    resp = resultado["resp"]
    assert resp.status_code == 409 and _codigo(resp) == "hoja_cerrada"
    with SessionLocal() as s:
        assert s.scalar(select(func.count()).select_from(Venta)) == 0
        assert s.get(HojaRuta, hoja["id"]) is not None


def test_la_carga_simultanea_de_dos_cargas_de_la_misma_hoja_descuenta_una_vez(reparto):
    r, pan = reparto, reparto["pan"]
    hoja = _hoja(r, (r["centro"], {pan: 10}))
    _confirmar(r, hoja["id"])
    with ThreadPoolExecutor(max_workers=4) as pool:
        estados = list(pool.map(lambda _: _cargar(r, hoja["id"]).status_code, range(4)))
    assert estados.count(200) == 1 and estados.count(409) == 3
    with SessionLocal() as s:
        p = s.get(Producto, pan)
        assert (p.stock_mostrador, p.stock_reservado) == (90, 0)
        assert s.scalar(select(func.count()).select_from(Turno)) == 1


def test_no_entregadas_simultaneas_asignan_orden_real_sin_repetir(reparto):
    """Las entregas no entregadas no toman remito: lo único que serializa `orden_real` es el
    bloqueo de la hoja."""
    r, pan = reparto, reparto["pan"]
    extra = [r["punto"](f"Local {i}", CENTRO) for i in range(4)]
    hoja = _en_ruta(r, (r["centro"], {pan: 1}), (r["norte"], {pan: 1}), *((p, {pan: 1}) for p in extra))
    clientes = [login("repa") for _ in hoja["entregas"]]

    def no_entregar(i):
        e = hoja["entregas"][i]
        cuerpo = {"operacion_id": str(uuid.uuid4()), "motivo": "Cerrado"}
        return clientes[i].post(f"{ENT}/{e['id']}/no-entregada", json=cuerpo)

    with ThreadPoolExecutor(max_workers=6) as pool:
        respuestas = list(pool.map(no_entregar, range(6)))
    assert [x.status_code for x in respuestas] == [200] * 6, [x.text for x in respuestas]
    assert sorted(x.json()["orden_real"] for x in respuestas) == [1, 2, 3, 4, 5, 6]
