"""Puntos de entrega, plantillas y cuenta corriente (libro inmutable)."""

import uuid
from decimal import Decimal

import pytest

from app.models import Cliente, RolEnum
from app.services import contabilidad

API = "/api/v1"
CC = f"{API}/contabilidad"


@pytest.fixture
def cliente(como):
    admin = como(RolEnum.ADMIN)
    c = admin.post(f"{API}/clientes", json={"nombre": "Bar del Puerto", "cuit": "30-71111111-9"})
    assert c.status_code == 201, c.text
    return {"admin": admin, **c.json()}


def _punto(admin, cliente_id, **extra):
    r = admin.post(f"{CC}/puntos-entrega", json={"cliente_id": cliente_id, "nombre": "Local 1", **extra})
    assert r.status_code == 201, r.text
    return r.json()


def _saldo(admin, cliente_id):
    return admin.get(f"{CC}/clientes/{cliente_id}/cuenta-corriente").json()["saldo"]


# ---------- Puntos de entrega ----------


def test_alta_y_edicion_de_un_punto(cliente):
    admin = cliente["admin"]
    p = _punto(admin, cliente["id"], direccion="Av. Mitre 100", latitud="-34.603722",
               longitud="-58.381592", ventana_desde="06:00", ventana_hasta="09:30",
               contacto="Marta", notas="Timbre 2")
    assert p["cliente_nombre"] == "Bar del Puerto"
    assert (p["latitud"], p["longitud"]) == (-34.603722, -58.381592)
    assert (p["ventana_desde"], p["ventana_hasta"]) == ("06:00:00", "09:30:00")
    assert p["dias_entrega"] == [] and p["activo"] is True

    r = admin.patch(f"{CC}/puntos-entrega/{p['id']}", json={"nombre": "Local Puerto", "contacto": None})
    assert r.status_code == 200
    assert (r.json()["nombre"], r.json()["contacto"], r.json()["direccion"]) == ("Local Puerto", None, "Av. Mitre 100")


def test_validaciones_del_punto(cliente):
    admin = cliente["admin"]
    base = {"cliente_id": cliente["id"], "nombre": "X"}
    assert admin.post(f"{CC}/puntos-entrega", json={**base, "latitud": "-34.6"}).status_code == 422
    assert admin.post(f"{CC}/puntos-entrega", json={**base, "latitud": "95", "longitud": "10"}).status_code == 422
    assert admin.post(f"{CC}/puntos-entrega", json={**base, "ventana_desde": "06:00"}).status_code == 422
    assert admin.post(f"{CC}/puntos-entrega",
                      json={**base, "ventana_desde": "10:00", "ventana_hasta": "08:00"}).status_code == 422
    assert admin.post(f"{CC}/puntos-entrega", json={**base, "nombre": ""}).status_code == 422
    assert admin.post(f"{CC}/puntos-entrega", json={"cliente_id": 9999, "nombre": "X"}).status_code == 404
    assert admin.post(f"{CC}/puntos-entrega", json={**base, "repartidor_habitual_id": 9999}).status_code == 404


def test_el_punto_no_cambia_de_cliente(cliente):
    admin = cliente["admin"]
    p = _punto(admin, cliente["id"])
    otro = admin.post(f"{API}/clientes", json={"nombre": "Otro"}).json()
    r = admin.patch(f"{CC}/puntos-entrega/{p['id']}", json={"cliente_id": otro["id"]})
    assert r.status_code == 200 and r.json()["cliente_id"] == cliente["id"]  # el campo se ignora


def test_listado_con_filtros_e_inactivos(cliente):
    admin = cliente["admin"]
    a = _punto(admin, cliente["id"], nombre="Alfa")
    _punto(admin, cliente["id"], nombre="Beta")
    admin.patch(f"{CC}/puntos-entrega/{a['id']}", json={"activo": False})
    assert [p["nombre"] for p in admin.get(f"{CC}/puntos-entrega").json()] == ["Beta"]
    todos = admin.get(f"{CC}/puntos-entrega", params={"incluir_inactivos": True}).json()
    assert [p["nombre"] for p in todos] == ["Alfa", "Beta"]
    assert [p["nombre"] for p in admin.get(f"{CC}/puntos-entrega", params={"buscar": "bet"}).json()] == ["Beta"]
    assert admin.get(f"{CC}/puntos-entrega", params={"cliente_id": 9999}).json() == []
    assert admin.get(f"{CC}/puntos-entrega/9999").status_code == 404


def test_un_cliente_con_varias_sucursales_comparte_cuenta(cliente):
    admin = cliente["admin"]
    _punto(admin, cliente["id"], nombre="Centro")
    _punto(admin, cliente["id"], nombre="Norte")
    assert len(admin.get(f"{CC}/puntos-entrega", params={"cliente_id": cliente["id"]}).json()) == 2


# ---------- Plantillas (pedido fijo por día) ----------


def test_plantillas_definen_los_dias_de_entrega(cliente, catalogo):
    admin = cliente["admin"]
    p = _punto(admin, cliente["id"])
    r = admin.put(f"{CC}/puntos-entrega/{p['id']}/plantillas", json={"dias": [
        {"dia_semana": 4, "items": [{"producto_id": catalogo["pan"], "cantidad": 30}]},
        {"dia_semana": 0, "items": [{"producto_id": catalogo["pan"], "cantidad": 20},
                                    {"producto_id": catalogo["medialuna"], "cantidad": 12}]},
    ]})
    assert r.status_code == 200, r.text
    assert [d["dia_semana"] for d in r.json()] == [0, 4]
    assert [(i["nombre"], i["cantidad"]) for i in r.json()[0]["items"]] == [("Pan", 20), ("Medialuna", 12)]
    assert admin.get(f"{CC}/puntos-entrega/{p['id']}").json()["dias_entrega"] == [0, 4]

    # Se reemplazan por completo; un día que desaparece deja de ser día de entrega
    admin.put(f"{CC}/puntos-entrega/{p['id']}/plantillas", json={"dias": [
        {"dia_semana": 2, "items": [{"producto_id": catalogo["medialuna"], "cantidad": 6}]}]})
    assert admin.get(f"{CC}/puntos-entrega/{p['id']}").json()["dias_entrega"] == [2]
    admin.put(f"{CC}/puntos-entrega/{p['id']}/plantillas", json={"dias": []})
    assert admin.get(f"{CC}/puntos-entrega/{p['id']}/plantillas").json() == []


def test_plantillas_invalidas(cliente, catalogo):
    admin = cliente["admin"]
    p = _punto(admin, cliente["id"])
    url = f"{CC}/puntos-entrega/{p['id']}/plantillas"
    item = {"producto_id": catalogo["pan"], "cantidad": 5}
    assert admin.put(url, json={"dias": [{"dia_semana": 7, "items": [item]}]}).status_code == 422
    assert admin.put(url, json={"dias": [{"dia_semana": 1, "items": []}]}).status_code == 422
    assert admin.put(url, json={"dias": [{"dia_semana": 1, "items": [item, item]}]}).status_code == 422
    assert admin.put(url, json={"dias": [{"dia_semana": 1, "items": [item]},
                                         {"dia_semana": 1, "items": [item]}]}).status_code == 422
    assert admin.put(url, json={"dias": [{"dia_semana": 1,
                                          "items": [{"producto_id": 9999, "cantidad": 1}]}]}).status_code == 404
    assert admin.put(url, json={"dias": [{"dia_semana": 1,
                                          "items": [{"producto_id": catalogo["pan"], "cantidad": 0}]}]}).status_code == 422


# ---------- Cuenta corriente ----------


def test_pago_nota_de_credito_y_ajuste_mueven_el_saldo(cliente):
    admin, cid = cliente["admin"], cliente["id"]
    admin.post(f"{CC}/clientes/{cid}/ajustes", json={"importe": 1000, "observacion": "Saldo inicial"})
    assert _saldo(admin, cid) == 1000.0

    pago = admin.post(f"{CC}/clientes/{cid}/pagos",
                      json={"monto": 300, "metodo_pago": "Transferencia", "referencia": "TR-1"})
    assert pago.status_code == 201, pago.text
    assert (pago.json()["tipo"], pago.json()["importe"], pago.json()["turno_id"]) == ("Pago", -300.0, None)
    assert _saldo(admin, cid) == 700.0

    nota = admin.post(f"{CC}/clientes/{cid}/notas-credito",
                      json={"monto": 50.5, "observacion": "Devolución de 20 panes"})
    assert nota.status_code == 201 and nota.json()["importe"] == -50.5
    assert _saldo(admin, cid) == 649.5

    cuenta = admin.get(f"{CC}/clientes/{cid}/cuenta-corriente").json()
    assert [m["tipo"] for m in cuenta["movimientos"]] == ["Nota de crédito", "Pago", "Ajuste"]
    assert cuenta["cuit"] == "30-71111111-9"


def test_el_saldo_a_favor_es_valido(cliente):
    admin, cid = cliente["admin"], cliente["id"]
    admin.post(f"{CC}/clientes/{cid}/pagos", json={"monto": 80, "metodo_pago": "Transferencia"})
    assert _saldo(admin, cid) == -80.0


def test_cobrar_en_efectivo_necesita_un_turno(cliente):
    admin, cid = cliente["admin"], cliente["id"]
    r = admin.post(f"{CC}/clientes/{cid}/pagos", json={"monto": 10, "metodo_pago": "Efectivo"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "sin_turno"
    assert _saldo(admin, cid) == 0.0
    admin.post(f"{API}/turnos", json={"efectivo_inicial": 0})
    ok = admin.post(f"{CC}/clientes/{cid}/pagos", json={"monto": 10, "metodo_pago": "Efectivo"})
    assert ok.status_code == 201 and ok.json()["turno_id"] is not None


def test_un_pago_no_puede_ser_con_cuenta_corriente(cliente):
    admin, cid = cliente["admin"], cliente["id"]
    r = admin.post(f"{CC}/clientes/{cid}/pagos", json={"monto": 10, "metodo_pago": "Cuenta corriente"})
    assert r.status_code == 422


@pytest.mark.parametrize(
    "ruta,cuerpo",
    [
        ("pagos", {"monto": 0, "metodo_pago": "Transferencia"}),
        ("pagos", {"monto": -5, "metodo_pago": "Transferencia"}),
        ("pagos", {"monto": 10.123, "metodo_pago": "Transferencia"}),
        ("notas-credito", {"monto": 10}),                                  # falta observación
        ("notas-credito", {"monto": 10, "observacion": ""}),
        ("ajustes", {"importe": 0, "observacion": "x"}),
        ("ajustes", {"importe": 10}),
    ],
)
def test_movimientos_invalidos(cliente, ruta, cuerpo):
    r = cliente["admin"].post(f"{CC}/clientes/{cliente['id']}/{ruta}", json=cuerpo)
    assert r.status_code == 422


def test_cliente_inexistente_o_dado_de_baja(cliente):
    admin = cliente["admin"]
    assert admin.post(f"{CC}/clientes/9999/pagos",
                      json={"monto": 1, "metodo_pago": "Transferencia"}).status_code == 404
    admin.patch(f"{API}/clientes/{cliente['id']}", json={"activo": False})
    assert admin.post(f"{CC}/clientes/{cliente['id']}/ajustes",
                      json={"importe": 5, "observacion": "x"}).status_code == 404


def test_un_ajuste_corrige_sin_tocar_el_original(cliente):
    admin, cid = cliente["admin"], cliente["id"]
    equivocado = admin.post(f"{CC}/clientes/{cid}/ajustes",
                            json={"importe": 500, "observacion": "Carga equivocada"}).json()
    fix = admin.post(f"{CC}/clientes/{cid}/ajustes",
                     json={"importe": -500, "observacion": "Anula carga equivocada",
                           "corrige_id": equivocado["id"]})
    assert fix.status_code == 201 and fix.json()["corrige_id"] == equivocado["id"]
    movimientos = admin.get(f"{CC}/clientes/{cid}/cuenta-corriente").json()["movimientos"]
    assert len(movimientos) == 2 and _saldo(admin, cid) == 0.0
    original = next(m for m in movimientos if m["id"] == equivocado["id"])
    assert original["importe"] == 500.0  # intacto


def test_no_se_corrige_un_movimiento_de_otro_cliente(cliente):
    admin = cliente["admin"]
    otro = admin.post(f"{API}/clientes", json={"nombre": "Otro"}).json()
    mov = admin.post(f"{CC}/clientes/{otro['id']}/ajustes", json={"importe": 10, "observacion": "x"}).json()
    r = admin.post(f"{CC}/clientes/{cliente['id']}/ajustes",
                   json={"importe": -10, "observacion": "y", "corrige_id": mov["id"]})
    assert r.status_code == 404
    assert _saldo(admin, cliente["id"]) == 0.0


def test_no_hay_forma_de_editar_ni_borrar_movimientos(cliente):
    admin, cid = cliente["admin"], cliente["id"]
    mov = admin.post(f"{CC}/clientes/{cid}/ajustes", json={"importe": 10, "observacion": "x"}).json()
    for metodo in (admin.delete, admin.put, admin.patch):
        r = metodo(f"{CC}/clientes/{cid}/movimientos/{mov['id']}")
        assert r.status_code in (404, 405)


# ---------- Idempotencia ----------


def test_reintentar_la_misma_operacion_no_duplica(cliente):
    admin, cid = cliente["admin"], cliente["id"]
    op = str(uuid.uuid4())
    cuerpo = {"monto": 100, "metodo_pago": "Transferencia", "operacion_id": op}
    primero = admin.post(f"{CC}/clientes/{cid}/pagos", json=cuerpo)
    segundo = admin.post(f"{CC}/clientes/{cid}/pagos", json=cuerpo)
    assert primero.status_code == segundo.status_code == 201
    assert primero.json()["id"] == segundo.json()["id"]
    assert _saldo(admin, cid) == -100.0


def test_operacion_reusada_en_otra_cosa_es_conflicto(cliente):
    admin, cid = cliente["admin"], cliente["id"]
    op = str(uuid.uuid4())
    admin.post(f"{CC}/clientes/{cid}/pagos", json={"monto": 10, "metodo_pago": "Transferencia", "operacion_id": op})
    r = admin.post(f"{CC}/clientes/{cid}/ajustes", json={"importe": 5, "observacion": "x", "operacion_id": op})
    assert r.status_code == 409 and r.json()["error"]["code"] == "operacion_en_curso"
    otro = admin.post(f"{API}/clientes", json={"nombre": "Otro"}).json()
    r = admin.post(f"{CC}/clientes/{otro['id']}/pagos",
                   json={"monto": 10, "metodo_pago": "Transferencia", "operacion_id": op})
    assert r.status_code == 409


# ---------- Saldo = suma de movimientos ----------


def test_el_saldo_es_siempre_la_suma_del_libro(cliente, catalogo, como, db):
    admin, cid = cliente["admin"], cliente["id"]
    vendedora = como(RolEnum.VENDEDORA)
    vendedora.post(f"{API}/turnos", json={"efectivo_inicial": 0})
    for cantidad in (1, 3):  # 100,50 y 301,50 a cuenta
        r = vendedora.post(f"{API}/ventas", json={
            "cliente_id": cid, "metodo_pago": "Cuenta corriente",
            "items": [{"producto_id": catalogo["pan"], "cantidad": cantidad}]})
        assert r.status_code == 201, r.text
    admin.post(f"{CC}/clientes/{cid}/pagos", json={"monto": 150.25, "metodo_pago": "Transferencia"})
    admin.post(f"{CC}/clientes/{cid}/notas-credito", json={"monto": 20, "observacion": "Merma"})
    admin.post(f"{CC}/clientes/{cid}/ajustes", json={"importe": -0.75, "observacion": "Redondeo"})

    cuenta = admin.get(f"{CC}/clientes/{cid}/cuenta-corriente").json()
    suma = sum(Decimal(str(m["importe"])) for m in cuenta["movimientos"])
    assert Decimal(str(cuenta["saldo"])) == suma == Decimal("231.00")
    assert contabilidad.verificar_saldos(db) == []


def test_verificar_saldos_detecta_un_saldo_corrupto(cliente, db):
    admin, cid = cliente["admin"], cliente["id"]
    admin.post(f"{CC}/clientes/{cid}/ajustes", json={"importe": 100, "observacion": "x"})
    db.get(Cliente, cid).saldo_cuenta_corriente = Decimal("90.00")  # alguien tocó el saldo a mano
    db.commit()
    assert contabilidad.verificar_saldos(db) == [
        {"cliente_id": cid, "saldo": Decimal("90.00"), "calculado": Decimal("100.00")}
    ]


def test_listado_de_saldos(cliente):
    admin = cliente["admin"]
    deudor = cliente["id"]
    sin_movimientos = admin.post(f"{API}/clientes", json={"nombre": "Nunca compró a cuenta"}).json()
    otro = admin.post(f"{API}/clientes", json={"nombre": "Al día"}).json()
    admin.post(f"{CC}/clientes/{deudor}/ajustes", json={"importe": 500, "observacion": "x"})
    admin.post(f"{CC}/clientes/{otro['id']}/ajustes", json={"importe": 50, "observacion": "x"})
    saldos = admin.get(f"{CC}/saldos").json()
    assert [(s["cliente"], s["saldo"]) for s in saldos] == [("Bar del Puerto", 500.0), ("Al día", 50.0)]
    assert sin_movimientos["id"] not in [s["cliente_id"] for s in saldos]


def test_filtro_por_fecha_de_los_movimientos(cliente):
    admin, cid = cliente["admin"], cliente["id"]
    admin.post(f"{CC}/clientes/{cid}/ajustes", json={"importe": 10, "observacion": "x"})
    hoy = admin.get(f"{CC}/clientes/{cid}/cuenta-corriente", params={"desde": "2000-01-01"}).json()
    assert len(hoy["movimientos"]) == 1
    futuro = admin.get(f"{CC}/clientes/{cid}/cuenta-corriente", params={"desde": "2999-01-01"}).json()
    assert futuro["movimientos"] == [] and futuro["saldo"] == 10.0  # el saldo no depende del filtro


# ---------- Permisos ----------

RUTAS_GESTION = [
    ("get", "/contabilidad/puntos-entrega", None),
    ("post", "/contabilidad/puntos-entrega", {"cliente_id": 1, "nombre": "X"}),
    ("get", "/contabilidad/saldos", None),
    ("get", "/contabilidad/clientes/1/cuenta-corriente", None),
    ("post", "/contabilidad/clientes/1/pagos", {"monto": 1, "metodo_pago": "Transferencia"}),
    ("post", "/contabilidad/clientes/1/notas-credito", {"monto": 1, "observacion": "x"}),
    ("post", "/contabilidad/clientes/1/ajustes", {"importe": 1, "observacion": "x"}),
]


@pytest.mark.parametrize("metodo,ruta,cuerpo", RUTAS_GESTION)
def test_sin_sesion_es_401(anonimo, metodo, ruta, cuerpo):
    r = getattr(anonimo, metodo)(API + ruta, **({"json": cuerpo} if cuerpo else {}))
    assert r.status_code == 401


@pytest.mark.parametrize("rol", [RolEnum.VENDEDORA, RolEnum.PANADERO])
@pytest.mark.parametrize("metodo,ruta,cuerpo", RUTAS_GESTION)
def test_los_operativos_no_ven_la_contabilidad(como, rol, metodo, ruta, cuerpo):
    c = como(rol)
    r = getattr(c, metodo)(API + ruta, **({"json": cuerpo} if cuerpo else {}))
    assert r.status_code == 403


def test_la_encargada_si_accede(como):
    c = como(RolEnum.ENCARGADA)
    assert c.get(f"{CC}/saldos").status_code == 200
    assert c.get(f"{CC}/puntos-entrega").status_code == 200
