from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.models import (
    Cliente,
    DetallePedido,
    EstadoPedidoEnum,
    MetodoPagoEnum,
    Pedido,
    Producto,
    RolEnum,
    Usuario,
)
from app.schemas.comercial import ItemPedido, PedidoCreate, PedidoUpdate
from app.services import caja, stock

E = EstadoPedidoEnum

# Transiciones manuales permitidas. ENTREGADO solo se alcanza cobrando (entregar()).
TRANSICIONES: dict[EstadoPedidoEnum, set[EstadoPedidoEnum]] = {
    E.PENDIENTE: {E.EN_PREPARACION, E.CANCELADO},
    E.EN_PREPARACION: {E.LISTO, E.PENDIENTE, E.CANCELADO},
    E.LISTO: {E.EN_PREPARACION, E.CANCELADO},
    E.ENTREGADO: set(),
    E.CANCELADO: set(),
}
ACTIVOS = (E.PENDIENTE, E.EN_PREPARACION, E.LISTO)


def _query():
    return select(Pedido).options(
        selectinload(Pedido.detalles).selectinload(DetallePedido.producto),
        selectinload(Pedido.cliente),
    )


def listar(
    db: Session,
    *,
    estados: list[EstadoPedidoEnum] | None = None,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    cliente_id: int | None = None,
) -> list[Pedido]:
    q = _query().order_by(Pedido.fecha_entrega, Pedido.id)
    if estados:
        q = q.where(Pedido.estado.in_(estados))
    if desde:
        q = q.where(Pedido.fecha_entrega >= desde)
    if hasta:
        q = q.where(Pedido.fecha_entrega < hasta)
    if cliente_id:
        q = q.where(Pedido.cliente_id == cliente_id)
    return list(db.scalars(q.limit(500)))


def obtener(db: Session, pedido_id: int) -> Pedido:
    pedido = db.scalar(_query().where(Pedido.id == pedido_id))
    if pedido is None:
        raise NotFoundError("Pedido no encontrado.")
    return pedido


def _armar_detalles(db: Session, items: list[ItemPedido]) -> tuple[list[DetallePedido], Decimal]:
    cantidades = stock.agrupar((i.producto_id, i.cantidad) for i in items)
    productos = {
        p.id: p for p in db.scalars(select(Producto).where(Producto.id.in_(cantidades.keys())))
    }
    faltantes = sorted(set(cantidades) - set(productos))
    if faltantes:
        raise NotFoundError(f"Producto(s) inexistente(s): {faltantes}.")
    inactivos = [p.nombre for p in productos.values() if not p.activo]
    if inactivos:
        raise ConflictError(f"Producto(s) dado(s) de baja: {', '.join(inactivos)}.")

    detalles, total = [], Decimal("0")
    for pid, cant in cantidades.items():
        precio = Decimal(productos[pid].precio_venta)
        subtotal = stock.redondear_dinero(precio * cant)
        total += subtotal
        detalles.append(
            DetallePedido(producto_id=pid, cantidad=cant, precio_unitario=precio, subtotal=subtotal)
        )
    return detalles, total


def crear(db: Session, usuario: Usuario, datos: PedidoCreate) -> Pedido:
    if datos.cliente_id is not None:
        cliente = db.get(Cliente, datos.cliente_id)
        if cliente is None or not cliente.activo:
            raise NotFoundError("Cliente no encontrado.")
    detalles, total = _armar_detalles(db, datos.items)
    pedido = Pedido(
        cliente_id=datos.cliente_id,
        contacto=datos.contacto,
        fecha_entrega=datos.fecha_entrega,
        notas=datos.notas,
        total=total,
        creado_por_id=usuario.id,
        detalles=detalles,
    )
    db.add(pedido)
    db.commit()
    return obtener(db, pedido.id)


def actualizar(db: Session, pedido_id: int, datos: PedidoUpdate) -> Pedido:
    pedido = obtener(db, pedido_id)
    if pedido.estado != E.PENDIENTE:
        raise ConflictError("Solo se pueden editar pedidos pendientes.")
    cambios = datos.model_dump(exclude_unset=True)
    if cambios.get("items"):
        detalles, total = _armar_detalles(db, datos.items)
        pedido.detalles.clear()
        db.flush()
        pedido.detalles.extend(detalles)
        pedido.total = total
    for campo in ("fecha_entrega", "notas", "contacto"):
        if campo in cambios and (cambios[campo] is not None or campo != "fecha_entrega"):
            setattr(pedido, campo, cambios[campo])
    db.commit()
    return obtener(db, pedido_id)


def cambiar_estado(db: Session, pedido_id: int, nuevo: EstadoPedidoEnum, usuario: Usuario) -> Pedido:
    pedido = obtener(db, pedido_id)
    if nuevo == E.ENTREGADO:
        raise ConflictError("Para entregar un pedido usá la acción de cobro.")
    if nuevo not in TRANSICIONES[pedido.estado]:
        raise ConflictError(
            f"No se puede pasar de '{pedido.estado.value}' a '{nuevo.value}'.",
            code="transicion_invalida",
        )
    if nuevo == E.CANCELADO and usuario.rol == RolEnum.PANADERO:
        raise ForbiddenError("Solo el mostrador o la gestión pueden cancelar pedidos.")
    pedido.estado = nuevo
    db.commit()
    return obtener(db, pedido_id)


def entregar(db: Session, pedido_id: int, usuario: Usuario, metodo_pago: MetodoPagoEnum) -> Pedido:
    """Cobra el pedido en el turno del usuario y descuenta el stock del mostrador."""
    turno = caja.exigir_turno_abierto(db, usuario)
    pedido = db.scalar(select(Pedido).where(Pedido.id == pedido_id).with_for_update())
    if pedido is None:
        raise NotFoundError("Pedido no encontrado.")
    if pedido.estado != E.LISTO:
        raise ConflictError("Solo se pueden entregar pedidos que estén listos.")

    venta = caja.crear_venta(
        db,
        usuario=usuario,
        turno=turno,
        items=[(d.producto_id, d.cantidad) for d in pedido.detalles],
        precios={d.producto_id: Decimal(d.precio_unitario) for d in pedido.detalles},
        metodo_pago=metodo_pago,
        cliente_id=pedido.cliente_id,
        commit=False,
    )
    pedido.estado = E.ENTREGADO
    pedido.venta_id = venta.id
    db.commit()
    return obtener(db, pedido_id)


def pendientes_produccion(
    db: Session, desde: datetime | None = None, hasta: datetime | None = None
) -> list[dict]:
    """Unidades comprometidas en pedidos activos vs. stock en mostrador."""
    q = (
        select(DetallePedido.producto_id, DetallePedido.cantidad)
        .join(Pedido)
        .where(Pedido.estado.in_((E.PENDIENTE, E.EN_PREPARACION)))
    )
    if desde:
        q = q.where(Pedido.fecha_entrega >= desde)
    if hasta:
        q = q.where(Pedido.fecha_entrega < hasta)
    pedidas: dict[int, int] = defaultdict(int)
    for pid, cant in db.execute(q):
        pedidas[pid] += cant
    if not pedidas:
        return []
    productos = {p.id: p for p in db.scalars(select(Producto).where(Producto.id.in_(pedidas)))}
    resultado = [
        {
            "producto_id": pid,
            "nombre": productos[pid].nombre,
            "cantidad_pedida": cant,
            "stock_mostrador": productos[pid].stock_mostrador,
            "faltante": max(0, cant - productos[pid].stock_mostrador),
        }
        for pid, cant in pedidas.items()
    ]
    return sorted(resultado, key=lambda r: (-r["faltante"], r["nombre"]))
