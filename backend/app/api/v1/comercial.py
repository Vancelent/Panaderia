from datetime import date

from fastapi import APIRouter, Query, status

from app.api.deps import DB, Interno, Mostrador
from app.models import EstadoPedidoEnum, Pedido
from app.schemas.comercial import (
    CambioEstadoPedido,
    ClienteCreate,
    ClienteOut,
    ClienteUpdate,
    EntregaPedido,
    PedidoCreate,
    PedidoOut,
    PedidoUpdate,
)
from app.services import clientes, finanzas, pedidos

router = APIRouter(tags=["Pedidos y clientes"])


def _pedido_out(p: Pedido) -> dict:
    return {
        "id": p.id, "cliente_id": p.cliente_id,
        "cliente_nombre": p.cliente.nombre if p.cliente else None,
        "contacto": p.contacto, "estado": p.estado, "fecha_entrega": p.fecha_entrega,
        "notas": p.notas, "total": p.total, "creado_en": p.creado_en, "venta_id": p.venta_id,
        "detalles": [
            {"producto_id": d.producto_id, "nombre": d.producto.nombre, "cantidad": d.cantidad,
             "precio_unitario": d.precio_unitario, "subtotal": d.subtotal}
            for d in p.detalles
        ],
    }


# ---------- Pedidos ----------


@router.get("/pedidos", response_model=list[PedidoOut])
def listar_pedidos(
    _: Interno,
    db: DB,
    estado: list[EstadoPedidoEnum] | None = Query(None),
    desde: date | None = None,
    hasta: date | None = None,
    cliente_id: int | None = None,
):
    """Por defecto devuelve los pedidos activos (pendientes, en preparación y listos)."""
    ini = finanzas.rango_local(desde, desde)[0] if desde else None
    fin = finanzas.rango_local(hasta, hasta)[1] if hasta else None
    estados = estado or (None if cliente_id else list(pedidos.ACTIVOS))
    return [
        _pedido_out(p)
        for p in pedidos.listar(db, estados=estados, desde=ini, hasta=fin, cliente_id=cliente_id)
    ]


@router.get("/pedidos/{pedido_id}", response_model=PedidoOut)
def ver_pedido(pedido_id: int, _: Interno, db: DB):
    return _pedido_out(pedidos.obtener(db, pedido_id))


@router.post("/pedidos", response_model=PedidoOut, status_code=status.HTTP_201_CREATED)
def crear_pedido(datos: PedidoCreate, usuario: Mostrador, db: DB):
    return _pedido_out(pedidos.crear(db, usuario, datos))


@router.patch("/pedidos/{pedido_id}", response_model=PedidoOut)
def editar_pedido(pedido_id: int, datos: PedidoUpdate, _: Mostrador, db: DB):
    return _pedido_out(pedidos.actualizar(db, pedido_id, datos))


@router.post("/pedidos/{pedido_id}/estado", response_model=PedidoOut)
def cambiar_estado(pedido_id: int, datos: CambioEstadoPedido, usuario: Interno, db: DB):
    return _pedido_out(pedidos.cambiar_estado(db, pedido_id, datos.estado, usuario))


@router.post("/pedidos/{pedido_id}/entrega", response_model=PedidoOut)
def entregar_pedido(pedido_id: int, datos: EntregaPedido, usuario: Mostrador, db: DB):
    """Cobra el pedido en el turno abierto del usuario y lo marca como entregado."""
    return _pedido_out(pedidos.entregar(db, pedido_id, usuario, datos.metodo_pago))


# ---------- Clientes ----------


@router.get("/clientes", response_model=list[ClienteOut])
def listar_clientes(_: Mostrador, db: DB, buscar: str | None = Query(None, max_length=60)):
    return clientes.listar(db, buscar=buscar)


@router.get("/clientes/{cliente_id}", response_model=ClienteOut)
def ver_cliente(cliente_id: int, _: Mostrador, db: DB):
    return clientes.obtener(db, cliente_id)


@router.post("/clientes", response_model=ClienteOut, status_code=status.HTTP_201_CREATED)
def crear_cliente(datos: ClienteCreate, _: Mostrador, db: DB):
    return clientes.crear(db, datos)


@router.patch("/clientes/{cliente_id}", response_model=ClienteOut)
def actualizar_cliente(cliente_id: int, datos: ClienteUpdate, _: Mostrador, db: DB):
    return clientes.actualizar(db, cliente_id, datos)
