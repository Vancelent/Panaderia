from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ConflictError, NotFoundError
from app.db.base import utcnow
from app.models import (
    Arqueo,
    Cliente,
    DetalleVenta,
    EstadoTurnoEnum,
    MetodoPagoEnum,
    Turno,
    Usuario,
    Venta,
)
from app.services import stock


def turno_abierto(db: Session, usuario: Usuario) -> Turno | None:
    return db.scalar(
        select(Turno).where(
            Turno.usuario_id == usuario.id, Turno.estado == EstadoTurnoEnum.ABIERTO
        )
    )


def exigir_turno_abierto(db: Session, usuario: Usuario) -> Turno:
    turno = turno_abierto(db, usuario)
    if turno is None:
        raise ConflictError("Abrí un turno de caja antes de cobrar.", code="sin_turno")
    return turno


def abrir_turno(db: Session, usuario: Usuario, efectivo_inicial: Decimal) -> Turno:
    if turno_abierto(db, usuario):
        raise ConflictError("Ya tenés un turno abierto.", code="turno_ya_abierto")
    turno = Turno(usuario_id=usuario.id, efectivo_inicial=efectivo_inicial)
    db.add(turno)
    try:
        db.commit()
    except IntegrityError:
        # Carrera entre dos aperturas simultáneas: el índice único la frena.
        db.rollback()
        raise ConflictError("Ya tenés un turno abierto.", code="turno_ya_abierto") from None
    return turno


def _totales_turno(db: Session, turno_id: int) -> tuple[Decimal, Decimal]:
    filas = db.execute(
        select(Venta.metodo_pago, func.coalesce(func.sum(Venta.monto), 0))
        .where(Venta.turno_id == turno_id)
        .group_by(Venta.metodo_pago)
    ).all()
    efectivo = sum((Decimal(t) for m, t in filas if m == MetodoPagoEnum.EFECTIVO), Decimal("0"))
    otros = sum((Decimal(t) for m, t in filas if m != MetodoPagoEnum.EFECTIVO), Decimal("0"))
    return stock.redondear_dinero(efectivo), stock.redondear_dinero(otros)


def cerrar_turno(db: Session, turno_id: int, monto_declarado: Decimal) -> Turno:
    """Arqueo ciego: se guarda la diferencia pero no se devuelve al cajero."""
    turno = db.scalar(select(Turno).where(Turno.id == turno_id).with_for_update())
    if turno is None:
        raise NotFoundError("Turno no encontrado.")
    if turno.estado == EstadoTurnoEnum.CERRADO:
        raise ConflictError("El turno ya fue cerrado.", code="turno_cerrado")

    ventas_efectivo, ventas_otros = _totales_turno(db, turno.id)
    monto_sistema = Decimal(turno.efectivo_inicial) + ventas_efectivo
    db.add(
        Arqueo(
            turno_id=turno.id,
            monto_sistema=monto_sistema,
            monto_declarado=monto_declarado,
            diferencia=monto_declarado - monto_sistema,
            ventas_efectivo=ventas_efectivo,
            ventas_otros_medios=ventas_otros,
        )
    )
    turno.estado = EstadoTurnoEnum.CERRADO
    turno.fecha_cierre = utcnow()
    db.commit()
    return turno


def crear_venta(
    db: Session,
    *,
    usuario: Usuario,
    turno: Turno,
    items: list[tuple[int, int]],
    metodo_pago: MetodoPagoEnum,
    cliente_id: int | None = None,
    precios: dict[int, Decimal] | None = None,
    commit: bool = True,
) -> Venta:
    """Descuenta stock y registra la venta en una sola transacción.

    `precios` permite respetar el precio pactado (p. ej. en un pedido); si no
    se indica, se usa el precio de lista actual. Los precios nunca vienen del
    cliente HTTP.
    """
    if cliente_id is not None and db.get(Cliente, cliente_id) is None:
        raise NotFoundError("Cliente no encontrado.")

    cantidades = stock.agrupar(items)
    productos = stock.bloquear_productos(db, cantidades.keys())
    stock.descontar_productos(productos, cantidades)

    venta = Venta(
        turno_id=turno.id,
        usuario_id=usuario.id,
        cliente_id=cliente_id,
        metodo_pago=metodo_pago,
        monto=Decimal("0"),
    )
    total = Decimal("0")
    for pid, cant in cantidades.items():
        precio = Decimal(precios[pid]) if precios and pid in precios else Decimal(productos[pid].precio_venta)
        subtotal = stock.redondear_dinero(precio * cant)
        total += subtotal
        venta.detalles.append(
            DetalleVenta(producto_id=pid, cantidad=cant, precio_unitario=precio, subtotal=subtotal)
        )
    venta.monto = total
    db.add(venta)
    if commit:
        db.commit()
    else:
        db.flush()
    return venta


def obtener_venta(db: Session, venta_id: int) -> Venta:
    venta = db.scalar(
        select(Venta)
        .where(Venta.id == venta_id)
        .options(selectinload(Venta.detalles).selectinload(DetalleVenta.producto))
    )
    if venta is None:
        raise NotFoundError("Venta no encontrada.")
    return venta


def ventas_de_turno(db: Session, turno_id: int, limite: int = 20) -> list[Venta]:
    return list(
        db.scalars(
            select(Venta)
            .where(Venta.turno_id == turno_id)
            .order_by(Venta.id.desc())
            .limit(limite)
            .options(selectinload(Venta.detalles).selectinload(DetalleVenta.producto))
        )
    )


def listar_arqueos(db: Session, limite: int = 100) -> list[Arqueo]:
    return list(
        db.scalars(
            select(Arqueo)
            .order_by(Arqueo.id.desc())
            .limit(limite)
            .options(selectinload(Arqueo.turno).selectinload(Turno.usuario))
        )
    )


def listar_turnos_abiertos(db: Session) -> list[Turno]:
    return list(
        db.scalars(
            select(Turno)
            .where(Turno.estado == EstadoTurnoEnum.ABIERTO)
            .options(selectinload(Turno.usuario))
        )
    )
