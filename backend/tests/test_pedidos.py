from datetime import UTC, datetime, timedelta

from app.models import RolEnum

API = "/api/v1"
MANANA = (datetime.now(UTC) + timedelta(days=1)).isoformat()


def _crear_pedido(c, catalogo, **extra):
    body = {"contacto": "Sra. Gómez", "fecha_entrega": MANANA,
            "items": [{"producto_id": catalogo["pan"], "cantidad": 4}], **extra}
    r = c.post(f"{API}/pedidos", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_pedido_requiere_cliente_o_contacto(como, catalogo):
    c = como(RolEnum.VENDEDORA)
    r = c.post(f"{API}/pedidos", json={"fecha_entrega": MANANA,
                                       "items": [{"producto_id": catalogo["pan"], "cantidad": 1}]})
    assert r.status_code == 422


def test_flujo_completo_de_pedido(como, catalogo):
    vendedora = como(RolEnum.VENDEDORA)
    panadero = como(RolEnum.PANADERO)
    cliente = vendedora.post(f"{API}/clientes", json={"nombre": "Bar La Esquina",
                                                     "telefono": "+54 11 5555-1234"}).json()
    pedido = _crear_pedido(vendedora, catalogo, cliente_id=cliente["id"], contacto=None)
    assert pedido["total"] == 402.0
    assert pedido["estado"] == "Pendiente"
    assert pedido["cliente_nombre"] == "Bar La Esquina"

    pendiente = panadero.get(f"{API}/produccion/pendiente").json()
    assert pendiente[0]["cantidad_pedida"] == 4

    pid = pedido["id"]
    assert panadero.post(f"{API}/pedidos/{pid}/estado", json={"estado": "En preparación"}).status_code == 200
    assert panadero.post(f"{API}/pedidos/{pid}/estado", json={"estado": "Listo"}).status_code == 200

    # Entregar exige turno abierto
    assert vendedora.post(f"{API}/pedidos/{pid}/entrega", json={}).status_code == 409
    vendedora.post(f"{API}/turnos", json={"efectivo_inicial": 0})
    r = vendedora.post(f"{API}/pedidos/{pid}/entrega", json={"metodo_pago": "Efectivo"})
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "Entregado"
    assert r.json()["venta_id"] is not None

    ventas = vendedora.get(f"{API}/turnos/actual/ventas").json()
    assert ventas[0]["monto"] == 402.0
    assert ventas[0]["cliente_id"] == cliente["id"]
    # Ya no aparece entre los activos
    assert all(p["id"] != pid for p in vendedora.get(f"{API}/pedidos").json())


def test_precio_pactado_se_respeta_al_entregar(como, catalogo):
    vendedora = como(RolEnum.VENDEDORA)
    admin = como(RolEnum.ADMIN)
    pedido = _crear_pedido(vendedora, catalogo)
    admin.patch(f"{API}/productos/{catalogo['pan']}", json={"precio_venta": 999})
    for estado in ("En preparación", "Listo"):
        vendedora.post(f"{API}/pedidos/{pedido['id']}/estado", json={"estado": estado})
    vendedora.post(f"{API}/turnos", json={"efectivo_inicial": 0})
    vendedora.post(f"{API}/pedidos/{pedido['id']}/entrega", json={})
    assert vendedora.get(f"{API}/turnos/actual/ventas").json()[0]["monto"] == 402.0


def test_transiciones_invalidas(como, catalogo):
    c = como(RolEnum.VENDEDORA)
    pedido = _crear_pedido(c, catalogo)
    r = c.post(f"{API}/pedidos/{pedido['id']}/estado", json={"estado": "Listo"})
    assert r.status_code == 409
    r = c.post(f"{API}/pedidos/{pedido['id']}/estado", json={"estado": "Entregado"})
    assert r.status_code == 409


def test_panadero_no_cancela(como, catalogo):
    c = como(RolEnum.VENDEDORA)
    panadero = como(RolEnum.PANADERO)
    pedido = _crear_pedido(c, catalogo)
    r = panadero.post(f"{API}/pedidos/{pedido['id']}/estado", json={"estado": "Cancelado"})
    assert r.status_code == 403
    assert c.post(f"{API}/pedidos/{pedido['id']}/estado", json={"estado": "Cancelado"}).status_code == 200


def test_editar_solo_pendiente(como, catalogo):
    c = como(RolEnum.VENDEDORA)
    pedido = _crear_pedido(c, catalogo)
    r = c.patch(f"{API}/pedidos/{pedido['id']}",
                json={"items": [{"producto_id": catalogo["medialuna"], "cantidad": 2}]})
    assert r.status_code == 200
    assert r.json()["total"] == 160.0
    c.post(f"{API}/pedidos/{pedido['id']}/estado", json={"estado": "En preparación"})
    r = c.patch(f"{API}/pedidos/{pedido['id']}", json={"notas": "sin sal"})
    assert r.status_code == 409


def test_busqueda_de_clientes(como):
    c = como(RolEnum.VENDEDORA)
    c.post(f"{API}/clientes", json={"nombre": "María López"})
    c.post(f"{API}/clientes", json={"nombre": "Juan Pérez"})
    r = c.get(f"{API}/clientes", params={"buscar": "maría"})
    nombres = [x["nombre"] for x in r.json()]
    assert "María López" in nombres and "Juan Pérez" not in nombres
    # Un intento de inyección se trata como texto
    assert c.get(f"{API}/clientes", params={"buscar": "' OR 1=1 --"}).json() == []
