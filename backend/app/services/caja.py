from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError, UnprocessableError
from app.db.base import utcnow
from app.models import (
    Arqueo,
    Cliente,
    DetalleVenta,
    EstadoPagoEnum,
    EstadoTurnoEnum,
    MetodoPagoEnum,
    OrigenVentaEnum,
    TipoTurnoEnum,
    Turno,
    Usuario,
    Venta,
    VentaPago,
)
from app.services import contabilidad, stock, turnos

CUENTA_CORRIENTE = MetodoPagoEnum.CUENTA_CORRIENTE


@dataclass(frozen=True)
class PagoEntrada:
    """Un medio de pago ya validado por el esquema (monto > 0, con 2 decimales)."""

    metodo_pago: MetodoPagoEnum
    monto: Decimal
    referencia: str | None = None


def medios_habilitados() -> list[MetodoPagoEnum]:
    return list(get_settings().medios_pago_habilitados)


def turno_abierto(
    db: Session, usuario: Usuario, tipo: TipoTurnoEnum = TipoTurnoEnum.MOSTRADOR
) -> Turno | None:
    return db.scalar(
        select(Turno).where(
            Turno.usuario_id == usuario.id,
            Turno.estado == EstadoTurnoEnum.ABIERTO,
            Turno.tipo == tipo,
        )
    )


def exigir_turno_abierto(
    db: Session, usuario: Usuario, tipo: TipoTurnoEnum = TipoTurnoEnum.MOSTRADOR
) -> Turno:
    turno = turno_abierto(db, usuario, tipo)
    if turno is None:
        if tipo == TipoTurnoEnum.REPARTO:
            raise ConflictError("No tenés una hoja de ruta cargada.", code="sin_turno")
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


def _totales_turno(db: Session, turno_id: int) -> tuple[Decimal, Decimal, Decimal]:
    """(ventas en efectivo, ventas en otros medios, cobros de cuenta corriente en efectivo).

    Sale de los pagos aprobados: en un pago mixto solo cuenta la parte en efectivo.
    La parte a cuenta corriente va en "otros medios": no entra al cajón.
    """
    filas = db.execute(
        select(VentaPago.metodo_pago, func.coalesce(func.sum(VentaPago.monto), 0))
        .join(Venta, Venta.id == VentaPago.venta_id)
        .where(Venta.turno_id == turno_id, VentaPago.estado == EstadoPagoEnum.APROBADO)
        .group_by(VentaPago.metodo_pago)
    ).all()
    efectivo = sum((Decimal(t) for m, t in filas if m == MetodoPagoEnum.EFECTIVO), Decimal("0"))
    otros = sum((Decimal(t) for m, t in filas if m != MetodoPagoEnum.EFECTIVO), Decimal("0"))
    cobros = contabilidad.cobros_efectivo_turno(db, turno_id)
    return stock.redondear_dinero(efectivo), stock.redondear_dinero(otros), cobros


def cerrar_turno(
    db: Session,
    turno_id: int,
    monto_declarado: Decimal,
    *,
    commit: bool = True,
    permitir_reparto: bool = False,
) -> Turno:
    """Arqueo ciego: se guarda la diferencia pero no se devuelve al cajero.

    El FOR UPDATE espera a que terminen las ventas y cobros en curso (que toman FOR SHARE
    sobre el turno), así ninguno queda fuera del arqueo.

    Un turno de reparto solo se cierra con la rendición de su hoja de ruta, que lo llama con
    `permitir_reparto=True` y `commit=False` para hacerlo todo en una sola transacción.
    """
    turno = db.scalar(
        select(Turno)
        .where(Turno.id == turno_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if turno is None:
        raise NotFoundError("Turno no encontrado.")
    if turno.estado == EstadoTurnoEnum.CERRADO:
        raise ConflictError("El turno ya fue cerrado.", code="turno_cerrado")
    if turno.tipo == TipoTurnoEnum.REPARTO and not permitir_reparto:
        raise ConflictError(
            "Un turno de reparto se cierra con la rendición de su hoja de ruta.",
            code="turno_de_reparto",
        )

    ventas_efectivo, ventas_otros, cobros = _totales_turno(db, turno.id)
    monto_sistema = Decimal(turno.efectivo_inicial) + ventas_efectivo + cobros
    db.add(
        Arqueo(
            turno_id=turno.id,
            monto_sistema=monto_sistema,
            monto_declarado=monto_declarado,
            diferencia=monto_declarado - monto_sistema,
            ventas_efectivo=ventas_efectivo,
            ventas_otros_medios=ventas_otros,
            cobros_efectivo=cobros,
        )
    )
    turno.estado = EstadoTurnoEnum.CERRADO
    turno.fecha_cierre = utcnow()
    if commit:
        db.commit()
    return turno


def validar_medios(medios: list[MetodoPagoEnum]) -> None:
    """La cuenta corriente se ofrece siempre que haya cliente; el resto, solo si está habilitado."""
    habilitados = set(medios_habilitados())
    no_habilitados = sorted({m.value for m in medios if m != CUENTA_CORRIENTE and m not in habilitados})
    if no_habilitados:
        raise UnprocessableError(
            f"Medio de pago no habilitado: {', '.join(no_habilitados)}.", code="medio_pago_no_habilitado"
        )


def _resolver_pagos(
    pagos: list[PagoEntrada] | None, metodo_pago: MetodoPagoEnum, total: Decimal
) -> list[PagoEntrada]:
    """Sin `pagos`, un único pago por el total. Con `pagos`, la suma debe cuadrar al centavo."""
    if pagos is None:
        return [PagoEntrada(metodo_pago, total)]
    pagado = sum((p.monto for p in pagos), Decimal("0"))
    if pagado != total:
        raise UnprocessableError(
            f"Los pagos ({pagado}) no suman el total de la venta ({total}).",
            code="pagos_no_cuadran",
            details={"total": float(total), "pagado": float(pagado)},
        )
    return pagos


def crear_venta(
    db: Session,
    *,
    usuario: Usuario,
    turno: Turno,
    items: list[tuple[int, int]],
    metodo_pago: MetodoPagoEnum,
    pagos: list[PagoEntrada] | None = None,
    cliente_id: int | None = None,
    precios: dict[int, Decimal] | None = None,
    origen: OrigenVentaEnum = OrigenVentaEnum.MOSTRADOR,
    commit: bool = True,
) -> Venta:
    """Descuenta stock y registra la venta con sus pagos en una sola transacción.

    Orden de bloqueos (jerarquía global, docs/rfc-001 §3.4): turno (share) → cliente
    (solo si hay cuenta corriente) → productos ordenados por id.

    `precios` permite respetar el precio pactado (p. ej. en un pedido); si no se indica,
    se usa el precio de lista actual. Ni los precios ni el total vienen del cliente HTTP.
    """
    # Validaciones baratas, antes de tomar ningún bloqueo
    medios = [p.metodo_pago for p in pagos] if pagos else [metodo_pago]
    validar_medios(medios)
    usa_cuenta_corriente = CUENTA_CORRIENTE in medios
    if usa_cuenta_corriente and cliente_id is None:
        raise UnprocessableError(
            "La venta a cuenta corriente necesita un cliente.", code="cliente_requerido"
        )

    turnos.bloquear_para_cobro(db, turno.id)

    cliente: Cliente | None = None
    if usa_cuenta_corriente:
        cliente = contabilidad.bloquear_cliente(db, cliente_id)
    elif cliente_id is not None:
        cliente = db.get(Cliente, cliente_id)
        if cliente is None:
            raise NotFoundError("Cliente no encontrado.")

    cantidades = stock.agrupar(items)
    productos = stock.bloquear_productos(db, cantidades.keys())

    # Se calcula y valida todo antes de tocar el stock: o se hace todo, o nada.
    venta = Venta(
        turno_id=turno.id, usuario_id=usuario.id, cliente_id=cliente_id,
        origen=origen, metodo_pago=metodo_pago, monto=Decimal("0"),
    )
    total = Decimal("0")
    for pid, cant in cantidades.items():
        precio = Decimal(precios[pid]) if precios and pid in precios else Decimal(productos[pid].precio_venta)
        subtotal = stock.redondear_dinero(precio * cant)
        total += subtotal
        venta.detalles.append(
            DetalleVenta(producto_id=pid, cantidad=cant, precio_unitario=precio, subtotal=subtotal)
        )
    pagos_finales = _resolver_pagos(pagos, metodo_pago, total)
    stock.descontar_productos(productos, cantidades)

    venta.monto = total
    venta.metodo_pago = max(pagos_finales, key=lambda p: p.monto).metodo_pago
    for p in pagos_finales:
        venta.pagos.append(
            VentaPago(
                metodo_pago=p.metodo_pago, monto=p.monto, referencia=p.referencia,
                estado=EstadoPagoEnum.APROBADO,
            )
        )
    db.add(venta)
    db.flush()  # necesitamos venta.id para el cargo en cuenta corriente

    if usa_cuenta_corriente:
        a_cuenta = sum(
            (p.monto for p in pagos_finales if p.metodo_pago == CUENTA_CORRIENTE), Decimal("0")
        )
        contabilidad.registrar_cargo_venta(db, cliente, venta, a_cuenta, usuario)

    if commit:
        db.commit()
    return venta


def obtener_venta(db: Session, venta_id: int) -> Venta:
    venta = db.scalar(
        select(Venta)
        .where(Venta.id == venta_id)
        .options(selectinload(Venta.detalles).selectinload(DetalleVenta.producto), selectinload(Venta.pagos))
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
            .options(
                selectinload(Venta.detalles).selectinload(DetalleVenta.producto),
                selectinload(Venta.pagos),
            )
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
