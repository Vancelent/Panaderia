"""Puntos de entrega, plantillas y cuenta corriente (módulo contable).

Este módulo no importa `services.caja`: es la caja la que usa el libro de cuenta corriente
(cargo por venta a cuenta). Los bloqueos siguen la jerarquía global de docs/rfc-001 §3.4;
acá solo interviene el nivel 5: la fila del cliente, siempre `FOR UPDATE` antes de tocar su saldo.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError, UnprocessableError
from app.models import (
    Cliente,
    MetodoPagoEnum,
    MovimientoCuentaCorriente,
    PlantillaEntrega,
    Producto,
    PuntoEntrega,
    TipoMovimientoCtaCteEnum,
    Usuario,
    Venta,
)
from app.schemas.contabilidad import (
    AjusteIn,
    NotaCreditoIn,
    PagoCuentaCorrienteIn,
    PlantillasIn,
    PuntoEntregaCreate,
    PuntoEntregaUpdate,
)
from app.services import finanzas

Tipo = TipoMovimientoCtaCteEnum

# ---------- Puntos de entrega ----------


def _cliente_activo(db: Session, cliente_id: int) -> Cliente:
    cliente = db.get(Cliente, cliente_id)
    if cliente is None or not cliente.activo:
        raise NotFoundError("Cliente no encontrado.")
    return cliente


def _validar_repartidor(db: Session, usuario_id: int) -> None:
    usuario = db.get(Usuario, usuario_id)
    if usuario is None or not usuario.activo:
        raise NotFoundError("Repartidor no encontrado.")


def _query_puntos():
    return select(PuntoEntrega).options(
        selectinload(PuntoEntrega.cliente), selectinload(PuntoEntrega.plantillas)
    )


def listar_puntos(
    db: Session,
    *,
    cliente_id: int | None = None,
    buscar: str | None = None,
    incluir_inactivos: bool = False,
) -> list[PuntoEntrega]:
    q = _query_puntos().order_by(PuntoEntrega.nombre)
    if not incluir_inactivos:
        q = q.where(PuntoEntrega.activo.is_(True))
    if cliente_id is not None:
        q = q.where(PuntoEntrega.cliente_id == cliente_id)
    if buscar:
        q = q.where(PuntoEntrega.nombre.ilike(f"%{buscar.strip()}%"))
    return list(db.scalars(q.limit(300)))


def obtener_punto(db: Session, punto_id: int) -> PuntoEntrega:
    punto = db.scalar(_query_puntos().where(PuntoEntrega.id == punto_id))
    if punto is None:
        raise NotFoundError("Punto de entrega no encontrado.")
    return punto


def crear_punto(db: Session, datos: PuntoEntregaCreate) -> PuntoEntrega:
    _cliente_activo(db, datos.cliente_id)
    if datos.repartidor_habitual_id is not None:
        _validar_repartidor(db, datos.repartidor_habitual_id)
    punto = PuntoEntrega(**datos.model_dump())
    db.add(punto)
    db.commit()
    return obtener_punto(db, punto.id)


def actualizar_punto(db: Session, punto_id: int, datos: PuntoEntregaUpdate) -> PuntoEntrega:
    punto = obtener_punto(db, punto_id)
    cambios = datos.model_dump(exclude_unset=True)
    if cambios.get("nombre") is None:
        cambios.pop("nombre", None)
    if cambios.get("activo") is None:
        cambios.pop("activo", None)
    if cambios.get("repartidor_habitual_id") is not None:
        _validar_repartidor(db, cambios["repartidor_habitual_id"])
    for campo, valor in cambios.items():
        setattr(punto, campo, valor)
    db.commit()
    return obtener_punto(db, punto_id)


def dias_entrega(punto: PuntoEntrega) -> list[int]:
    return sorted({p.dia_semana for p in punto.plantillas})


# ---------- Plantillas ----------


def obtener_plantillas(db: Session, punto_id: int) -> list[dict]:
    obtener_punto(db, punto_id)
    filas = db.scalars(
        select(PlantillaEntrega)
        .where(PlantillaEntrega.punto_entrega_id == punto_id)
        .options(selectinload(PlantillaEntrega.producto))
        .order_by(PlantillaEntrega.dia_semana, PlantillaEntrega.id)
    )
    dias: dict[int, list[dict]] = {}
    for f in filas:
        dias.setdefault(f.dia_semana, []).append(
            {"producto_id": f.producto_id, "nombre": f.producto.nombre, "cantidad": f.cantidad}
        )
    return [{"dia_semana": d, "items": items} for d, items in sorted(dias.items())]


def reemplazar_plantillas(db: Session, punto_id: int, datos: PlantillasIn) -> list[dict]:
    punto = obtener_punto(db, punto_id)
    pedidos = {i.producto_id for d in datos.dias for i in d.items}
    if pedidos:
        activos = set(
            db.scalars(select(Producto.id).where(Producto.id.in_(pedidos), Producto.activo.is_(True)))
        )
        faltantes = sorted(pedidos - activos)
        if faltantes:
            raise NotFoundError(
                f"Producto(s) inexistente(s) o dado(s) de baja: {faltantes}.", details={"ids": faltantes}
            )
    punto.plantillas.clear()
    db.flush()
    for dia in datos.dias:
        for item in dia.items:
            punto.plantillas.append(
                PlantillaEntrega(
                    dia_semana=dia.dia_semana, producto_id=item.producto_id, cantidad=item.cantidad
                )
            )
    db.commit()
    return obtener_plantillas(db, punto_id)


# ---------- Cuenta corriente ----------


def bloquear_cliente(db: Session, cliente_id: int) -> Cliente:
    """FOR UPDATE sobre el cliente (nivel 5): serializa los cambios de saldo."""
    cliente = db.scalar(
        select(Cliente)
        .where(Cliente.id == cliente_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if cliente is None or not cliente.activo:
        raise NotFoundError("Cliente no encontrado.")
    return cliente


def _aplicar(
    db: Session, cliente: Cliente, usuario: Usuario, tipo: Tipo, importe: Decimal, **extra
) -> MovimientoCuentaCorriente:
    """Agrega el movimiento y actualiza el saldo cacheado. El cliente ya está bloqueado."""
    movimiento = MovimientoCuentaCorriente(
        cliente_id=cliente.id, tipo=tipo, importe=importe, usuario_id=usuario.id, **extra
    )
    db.add(movimiento)
    cliente.saldo_cuenta_corriente = Decimal(cliente.saldo_cuenta_corriente) + importe
    db.flush()
    return movimiento


def registrar_cargo_venta(
    db: Session,
    cliente: Cliente,
    venta: Venta,
    monto: Decimal,
    usuario: Usuario,
    punto_entrega_id: int | None = None,
) -> MovimientoCuentaCorriente:
    """Cargo por la parte de una venta que quedó a cuenta. Lo llaman la caja y el reparto, con el
    cliente ya bloqueado."""
    return _aplicar(
        db, cliente, usuario, Tipo.CARGO, monto,
        venta_id=venta.id, turno_id=venta.turno_id, observacion=f"Venta #{venta.id}",
        punto_entrega_id=punto_entrega_id,
    )


def _movimiento_previo(
    db: Session, operacion_id: UUID | None, cliente_id: int, tipo: Tipo
) -> MovimientoCuentaCorriente | None:
    """Idempotencia: si la operación ya se aplicó, se devuelve el movimiento existente.

    Se consulta DESPUÉS de bloquear al cliente: dos reintentos simultáneos se serializan
    y el segundo encuentra el movimiento del primero.
    """
    if operacion_id is None:
        return None
    previo = db.scalar(
        select(MovimientoCuentaCorriente).where(MovimientoCuentaCorriente.operacion_id == operacion_id)
    )
    if previo is not None and (previo.cliente_id != cliente_id or previo.tipo != tipo):
        raise ConflictError(
            "Ese identificador de operación ya se usó en otra operación.", code="operacion_en_curso"
        )
    return previo


def _validar_corrige(db: Session, cliente_id: int, corrige_id: int | None) -> None:
    if corrige_id is None:
        return
    original = db.get(MovimientoCuentaCorriente, corrige_id)
    if original is None or original.cliente_id != cliente_id:
        raise NotFoundError("El movimiento a corregir no existe en esta cuenta.")


def _guardar(db: Session, movimiento: MovimientoCuentaCorriente) -> MovimientoCuentaCorriente:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError(
            "Esa operación ya fue registrada.", code="operacion_en_curso"
        ) from None
    return movimiento


def registrar_pago(
    db: Session,
    usuario: Usuario,
    cliente_id: int,
    datos: PagoCuentaCorrienteIn,
    turno_id: int | None = None,
) -> MovimientoCuentaCorriente:
    """Cobro de deuda. En efectivo debe llevar el `turno_id` ya bloqueado FOR SHARE (nivel 2)
    para que el dinero cuente en el arqueo de ese turno."""
    if datos.metodo_pago not in get_settings().medios_pago_habilitados:
        raise UnprocessableError(
            f"Medio de pago no habilitado: {datos.metodo_pago.value}.", code="medio_pago_no_habilitado"
        )
    if datos.metodo_pago == MetodoPagoEnum.EFECTIVO and turno_id is None:
        raise ConflictError(
            "Para cobrar en efectivo abrí un turno de caja, o registrá el pago como transferencia.",
            code="sin_turno",
        )
    cliente = bloquear_cliente(db, cliente_id)
    previo = _movimiento_previo(db, datos.operacion_id, cliente_id, Tipo.PAGO)
    if previo is not None:
        return previo
    movimiento = _aplicar(
        db, cliente, usuario, Tipo.PAGO, -datos.monto,
        metodo_pago=datos.metodo_pago, referencia=datos.referencia, observacion=datos.observacion,
        turno_id=turno_id if datos.metodo_pago == MetodoPagoEnum.EFECTIVO else None,
        operacion_id=datos.operacion_id,
    )
    return _guardar(db, movimiento)


def registrar_nota_credito(
    db: Session, usuario: Usuario, cliente_id: int, datos: NotaCreditoIn
) -> MovimientoCuentaCorriente:
    """Reduce la deuda (p. ej. mercadería devuelta). No mueve efectivo ni stock."""
    cliente = bloquear_cliente(db, cliente_id)
    previo = _movimiento_previo(db, datos.operacion_id, cliente_id, Tipo.NOTA_CREDITO)
    if previo is not None:
        return previo
    _validar_corrige(db, cliente_id, datos.corrige_id)
    movimiento = _aplicar(
        db, cliente, usuario, Tipo.NOTA_CREDITO, -datos.monto,
        observacion=datos.observacion, corrige_id=datos.corrige_id, operacion_id=datos.operacion_id,
    )
    return _guardar(db, movimiento)


def registrar_ajuste(
    db: Session, usuario: Usuario, cliente_id: int, datos: AjusteIn
) -> MovimientoCuentaCorriente:
    """Corrige un error con un movimiento nuevo; el original no se toca."""
    cliente = bloquear_cliente(db, cliente_id)
    previo = _movimiento_previo(db, datos.operacion_id, cliente_id, Tipo.AJUSTE)
    if previo is not None:
        return previo
    _validar_corrige(db, cliente_id, datos.corrige_id)
    movimiento = _aplicar(
        db, cliente, usuario, Tipo.AJUSTE, datos.importe,
        observacion=datos.observacion, corrige_id=datos.corrige_id, operacion_id=datos.operacion_id,
    )
    return _guardar(db, movimiento)


def cobros_efectivo_turno(db: Session, turno_id: int) -> Decimal:
    """Efectivo cobrado de cuentas corrientes dentro de un turno (suma al efectivo esperado)."""
    total = db.scalar(
        select(func.coalesce(func.sum(-MovimientoCuentaCorriente.importe), 0)).where(
            MovimientoCuentaCorriente.turno_id == turno_id,
            MovimientoCuentaCorriente.tipo == Tipo.PAGO,
            MovimientoCuentaCorriente.metodo_pago == MetodoPagoEnum.EFECTIVO,
        )
    )
    return Decimal(total or 0)


def obtener_cuenta(db: Session, cliente_id: int) -> Cliente:
    cliente = db.get(Cliente, cliente_id)
    if cliente is None:
        raise NotFoundError("Cliente no encontrado.")
    return cliente


def listar_movimientos(
    db: Session,
    cliente_id: int,
    *,
    desde: date | None = None,
    hasta: date | None = None,
    limite: int = 500,
) -> list[MovimientoCuentaCorriente]:
    q = (
        select(MovimientoCuentaCorriente)
        .where(MovimientoCuentaCorriente.cliente_id == cliente_id)
        .options(selectinload(MovimientoCuentaCorriente.usuario))
        .order_by(MovimientoCuentaCorriente.id.desc())
        .limit(limite)
    )
    if desde:
        q = q.where(MovimientoCuentaCorriente.fecha >= finanzas.rango_local(desde, desde)[0])
    if hasta:
        q = q.where(MovimientoCuentaCorriente.fecha < finanzas.rango_local(hasta, hasta)[1])
    return list(db.scalars(q))


def listar_saldos(db: Session) -> list[dict]:
    """Clientes que tienen o tuvieron cuenta corriente, con su saldo."""
    filas = db.execute(
        select(Cliente, func.max(MovimientoCuentaCorriente.fecha))
        .join(MovimientoCuentaCorriente, MovimientoCuentaCorriente.cliente_id == Cliente.id)
        .group_by(Cliente.id)
        .order_by(Cliente.saldo_cuenta_corriente.desc(), Cliente.nombre)
    ).all()
    return [
        {
            "cliente_id": c.id, "cliente": c.nombre, "saldo": c.saldo_cuenta_corriente,
            "ultimo_movimiento": ultimo,
        }
        for c, ultimo in filas
    ]


def verificar_saldos(db: Session) -> list[dict]:
    """Compara el saldo cacheado de cada cliente con la suma de su libro.

    Devuelve solo las diferencias (lista vacía = todo consistente). Pensado para el
    `cron` de verificación y para el tablero.
    """
    mov = MovimientoCuentaCorriente
    calculado = dict(db.execute(select(mov.cliente_id, func.sum(mov.importe)).group_by(mov.cliente_id)).all())
    diferencias = []
    for cliente in db.scalars(select(Cliente)):
        esperado = Decimal(calculado.get(cliente.id) or 0)
        if Decimal(cliente.saldo_cuenta_corriente) != esperado:
            diferencias.append(
                {"cliente_id": cliente.id, "saldo": cliente.saldo_cuenta_corriente, "calculado": esperado}
            )
    return diferencias
