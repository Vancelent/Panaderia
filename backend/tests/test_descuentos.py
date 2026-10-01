"""Descuentos por punto de entrega: precedencia, vigencia y precisión Decimal."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models import RolEnum
from app.services import descuentos

API = "/api/v1"
HOY = date.today()


@pytest.fixture
def punto(como):
    """Punto de entrega de un cliente mayorista, creado como lo haría el admin."""
    admin = como(RolEnum.ADMIN)
    cliente = admin.post(f"{API}/clientes", json={"nombre": "Distribuidora Sur"}).json()
    r = admin.post(f"{API}/contabilidad/puntos-entrega",
                   json={"cliente_id": cliente["id"], "nombre": "Sucursal Centro"})
    assert r.status_code == 201, r.text
    return {"admin": admin, "id": r.json()["id"], "cliente_id": cliente["id"]}


def _descuento(punto, porcentaje, producto_id=None, **extra):
    r = punto["admin"].post(
        f"{API}/contabilidad/puntos-entrega/{punto['id']}/descuentos",
        json={"porcentaje": porcentaje, "motivo": "Mayorista", "producto_id": producto_id, **extra},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _precios(db, punto, catalogo, fecha=HOY):
    return descuentos.resolver_precios(db, punto["id"], [catalogo["pan"], catalogo["medialuna"]], fecha)


def test_sin_descuentos_es_precio_de_lista(punto, catalogo, db):
    p = _precios(db, punto, catalogo)
    assert p[catalogo["pan"]].precio_unitario == Decimal("100.50")
    assert p[catalogo["pan"]].descuento_pct is None and p[catalogo["pan"]].descuento_id is None


def test_el_descuento_del_producto_gana_al_general(punto, catalogo, db):
    general = _descuento(punto, 10)
    pan = _descuento(punto, 25, catalogo["pan"], motivo="Pan del día anterior")
    p = _precios(db, punto, catalogo)
    # Pan: 25 % de 100,50 = 75,375 -> 75,38 (redondeo comercial)
    assert p[catalogo["pan"]].precio_unitario == Decimal("75.38")
    assert (p[catalogo["pan"]].descuento_pct, p[catalogo["pan"]].descuento_id) == (Decimal("25.00"), pan["id"])
    # Medialuna: no tiene propio, aplica el general: 80 - 10 % = 72
    assert p[catalogo["medialuna"]].precio_unitario == Decimal("72.00")
    assert p[catalogo["medialuna"]].descuento_id == general["id"]


def test_los_descuentos_no_se_suman(punto, catalogo, db):
    _descuento(punto, 10)
    _descuento(punto, 20, catalogo["pan"])
    p = _precios(db, punto, catalogo)
    assert p[catalogo["pan"]].precio_unitario == Decimal("80.40")  # solo 20 %, no 28 % ni 30 %


def test_entre_varios_del_mismo_nivel_gana_el_mayor_porcentaje(punto, catalogo, db):
    _descuento(punto, 5)
    _descuento(punto, 12)
    _descuento(punto, 8)
    p = _precios(db, punto, catalogo)
    assert p[catalogo["medialuna"]].descuento_pct == Decimal("12.00")
    assert p[catalogo["medialuna"]].precio_unitario == Decimal("70.40")


def test_vigencia_y_estado(punto, catalogo, db):
    ayer, manana = HOY - timedelta(days=1), HOY + timedelta(days=1)
    _descuento(punto, 50, catalogo["pan"], vigente_hasta=ayer.isoformat())           # vencido
    _descuento(punto, 40, catalogo["pan"], vigente_desde=manana.isoformat())         # futuro
    inactivo = _descuento(punto, 30, catalogo["pan"])
    punto["admin"].patch(f"{API}/contabilidad/puntos-entrega/{punto['id']}/descuentos/{inactivo['id']}",
                         json={"activo": False})
    vigente = _descuento(punto, 15, catalogo["pan"], vigente_desde=ayer.isoformat(),
                         vigente_hasta=manana.isoformat())

    assert _precios(db, punto, catalogo)[catalogo["pan"]].descuento_id == vigente["id"]
    # Mañana, en cambio, rige el del futuro (40 %) y el de 15 % también: gana el mayor
    p_manana = _precios(db, punto, catalogo, fecha=manana)
    assert p_manana[catalogo["pan"]].descuento_pct == Decimal("40.00")


def test_descuento_de_otro_punto_no_aplica(punto, catalogo, db, como):
    admin = punto["admin"]
    otro = admin.post(f"{API}/contabilidad/puntos-entrega",
                      json={"cliente_id": punto["cliente_id"], "nombre": "Sucursal Norte"}).json()
    admin.post(f"{API}/contabilidad/puntos-entrega/{otro['id']}/descuentos",
               json={"porcentaje": 30, "motivo": "Otro"})
    assert _precios(db, punto, catalogo)[catalogo["pan"]].precio_unitario == Decimal("100.50")


def test_descuento_total_es_gratis_y_nunca_negativo(punto, catalogo, db):
    _descuento(punto, 100)
    assert _precios(db, punto, catalogo)[catalogo["pan"]].precio_unitario == Decimal("0.00")


@pytest.mark.parametrize(
    "lista,pct,esperado",
    [
        ("0.10", "15", "0.09"),        # 0,085 -> 0,09 (mitad hacia arriba)
        ("100.00", "33.33", "66.67"),
        ("19.99", "7.5", "18.49"),     # 18,490750 -> 18,49
        ("1000.00", "0.01", "999.90"),
        ("500.00", None, "500.00"),
    ],
)
def test_precio_con_descuento_es_exacto_con_decimal(lista, pct, esperado):
    r = descuentos.precio_con_descuento(Decimal(lista), Decimal(pct) if pct else None)
    assert isinstance(r, Decimal) and r == Decimal(esperado)


def test_producto_inexistente(punto, db):
    with pytest.raises(Exception) as e:
        descuentos.resolver_precios(db, punto["id"], [9999], HOY)
    assert "inexistente" in str(e.value)


# ---------- API ----------


@pytest.mark.parametrize("porcentaje", [0, -5, 100.01, 101, "abc", 12.345])
def test_porcentaje_invalido(punto, porcentaje):
    r = punto["admin"].post(f"{API}/contabilidad/puntos-entrega/{punto['id']}/descuentos",
                            json={"porcentaje": porcentaje, "motivo": "x"})
    assert r.status_code == 422


def test_vigencia_invertida(punto):
    r = punto["admin"].post(
        f"{API}/contabilidad/puntos-entrega/{punto['id']}/descuentos",
        json={"porcentaje": 10, "motivo": "x", "vigente_desde": "2026-10-10", "vigente_hasta": "2026-10-01"},
    )
    assert r.status_code == 422


def test_descuento_de_producto_inexistente_o_punto_ajeno(punto):
    admin = punto["admin"]
    r = admin.post(f"{API}/contabilidad/puntos-entrega/{punto['id']}/descuentos",
                   json={"porcentaje": 10, "motivo": "x", "producto_id": 9999})
    assert r.status_code == 404
    d = _descuento(punto, 10)
    assert admin.patch(f"{API}/contabilidad/puntos-entrega/9999/descuentos/{d['id']}",
                       json={"porcentaje": 5}).status_code == 404


def test_listado_de_descuentos_y_edicion(punto, catalogo):
    _descuento(punto, 10)
    d = _descuento(punto, 20, catalogo["pan"], motivo="Día anterior")
    lista = punto["admin"].get(f"{API}/contabilidad/puntos-entrega/{punto['id']}/descuentos").json()
    assert [(x["porcentaje"], x["producto_nombre"]) for x in lista] == [(10.0, None), (20.0, "Pan")]
    r = punto["admin"].patch(f"{API}/contabilidad/puntos-entrega/{punto['id']}/descuentos/{d['id']}",
                             json={"porcentaje": 22.5, "motivo": "Más liquidación"})
    assert r.status_code == 200 and (r.json()["porcentaje"], r.json()["motivo"]) == (22.5, "Más liquidación")


@pytest.mark.parametrize("rol", [RolEnum.VENDEDORA, RolEnum.PANADERO])
def test_los_operativos_no_tocan_descuentos(punto, como, rol):
    c = como(rol)
    base = f"{API}/contabilidad/puntos-entrega/{punto['id']}/descuentos"
    assert c.get(base).status_code == 403
    assert c.post(base, json={"porcentaje": 10, "motivo": "x"}).status_code == 403
