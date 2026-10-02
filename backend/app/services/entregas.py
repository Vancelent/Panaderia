"""Reparto matutino: hojas de ruta, carga del vehículo, entregas y rendición (docs/rfc-001 §3).

Cada operación es una única transacción (un `commit` al final; ante cualquier error, rollback).
Los bloqueos siguen la jerarquía global de docs/rfc-001 §3.4:

    1 idempotencia → 2 turno → 3 hoja → 4 entregas → 5 cliente → 6 numerador → 7 productos

Los bloqueos de hoja y entrega son `FOR NO KEY UPDATE`: igual de exclusivos entre sí, pero no frenan
el `INSERT` de puntos GPS ni de eventos, que solo toman `FOR KEY SHARE` sobre la fila por su FK.
"""

from collections import defaultdict
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, UnprocessableError
from app.db.base import utcnow
from app.db.utils import insertar_nuevos
from app.models import (
    Cliente,
    DestinoDevolucionEnum,
    DetalleVenta,
    Entrega,
    EntregaEvento,
    EntregaItem,
    EstadoEntregaEnum,
    EstadoHojaRutaEnum,
    EstadoPagoEnum,
    EstadoTurnoEnum,
    HojaRuta,
    HojaRutaItem,
    Merma,
    MetodoPagoEnum,
    Numerador,
    OrigenVentaEnum,
    PlantillaEntrega,
    Producto,
    PuntoEntrega,
    RecorridoPunto,
    RolEnum,
    TipoEventoEntregaEnum,
    TipoTurnoEnum,
    Turno,
    Usuario,
    Venta,
    VentaPago,
)
from app.schemas.entregas import (
    CargaIn,
    CargaItemOut,
    ConfirmacionEntregaIn,
    EntregaOut,
    GeneracionOut,
    HojaRutaCreate,
    HojaRutaOut,
    HojaRutaResumenOut,
    HojaRutaUpdate,
    InicioRutaIn,
    ItemEntregaOut,
    ItemHojaIn,
    NoEntregadaIn,
    OmitidoOut,
    OperacionMovil,
    ParadaIn,
    PosicionIn,
    RecorridoLoteIn,
    RendicionIn,
    ResumenEntregasOut,
)
from app.services import caja, contabilidad, descuentos, idempotencia, recorrido, rutas, stock, turnos

H = EstadoHojaRutaEnum
E = EstadoEntregaEnum
CERO = Decimal("0")
DOS_DECIMALES = Decimal("0.01")
ABIERTAS = (E.PENDIENTE, E.EN_LOCAL)  # entregas que todavía no se resolvieron
CERRADAS = (H.RENDIDA, H.ANULADA)
MOTIVO_DEVOLUCION = "Devolución de reparto"


# ---------- Consultas y bloqueos ----------


def _query_hoja():
    return (
        select(HojaRuta)
        .options(
            selectinload(HojaRuta.repartidor),
            selectinload(HojaRuta.items).selectinload(HojaRutaItem.producto),
            selectinload(HojaRuta.entregas).selectinload(Entrega.punto).selectinload(PuntoEntrega.cliente),
            selectinload(HojaRuta.entregas).selectinload(Entrega.items).selectinload(EntregaItem.producto),
        )
        .execution_options(populate_existing=True)
    )


def _query_entrega():
    return (
        select(Entrega)
        .options(
            selectinload(Entrega.punto).selectinload(PuntoEntrega.cliente),
            selectinload(Entrega.items).selectinload(EntregaItem.producto),
        )
        .execution_options(populate_existing=True)
    )


def _obtener_hoja(db: Session, hoja_id: int) -> HojaRuta:
    hoja = db.scalar(_query_hoja().where(HojaRuta.id == hoja_id))
    if hoja is None:
        raise NotFoundError("Hoja de ruta no encontrada.")
    return hoja


def _bloquear_hoja(db: Session, hoja_id: int) -> HojaRuta:
    """Nivel 3. `populate_existing`: la hoja puede haber cambiado desde que se leyó."""
    hoja = db.scalar(
        select(HojaRuta)
        .where(HojaRuta.id == hoja_id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )
    if hoja is None:
        raise NotFoundError("Hoja de ruta no encontrada.")
    return hoja


def _bloquear_entregas(db: Session, hoja_id: int) -> list[Entrega]:
    """Nivel 4: todas las entregas de la hoja, ordenadas por id."""
    return list(
        db.scalars(
            select(Entrega)
            .where(Entrega.hoja_id == hoja_id)
            .order_by(Entrega.id)
            .options(selectinload(Entrega.items), selectinload(Entrega.punto))
            .with_for_update(key_share=True)
            .execution_options(populate_existing=True)
        )
    )


def _items_hoja(db: Session, hoja_id: int) -> list[HojaRutaItem]:
    return list(
        db.scalars(
            select(HojaRutaItem)
            .where(HojaRutaItem.hoja_id == hoja_id)
            .order_by(HojaRutaItem.id)
            .options(selectinload(HojaRutaItem.producto))
            .execution_options(populate_existing=True)
        )
    )


def _hoja_cerrada() -> ConflictError:
    return ConflictError("La hoja de ruta ya fue rendida o anulada.", code="hoja_cerrada")


def _transicion_invalida(hoja: HojaRuta, accion: str) -> ConflictError:
    return ConflictError(
        f"No se puede {accion} una hoja en estado '{hoja.estado.value}'.", code="transicion_invalida"
    )


def _exigir_repartidor(hoja_repartidor_id: int, usuario: Usuario) -> None:
    if hoja_repartidor_id != usuario.id:
        raise ForbiddenError("Esta hoja de ruta no es tuya.")


# ---------- Idempotencia ----------


def _operar(
    db: Session, usuario: Usuario, operacion_id: UUID, tipo: str, accion: Callable[[], BaseModel]
) -> dict:
    """Ejecuta una operación de la app una sola vez por `operacion_id`.

    Un reintento (de una operación ya completada) devuelve la respuesta guardada sin repetir nada.
    Si la operación falla, el rollback también descarta la reserva de la clave: se puede reintentar.
    """
    previa = idempotencia.iniciar(db, operacion_id, usuario, tipo)
    if previa is not None:
        db.rollback()
        return previa
    try:
        respuesta = idempotencia.completar(db, operacion_id, accion().model_dump(mode="json"))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return respuesta


# ---------- Armado de hojas ----------


def _validar_repartidor(db: Session, repartidor_id: int) -> Usuario:
    usuario = db.get(Usuario, repartidor_id)
    if usuario is None or not usuario.activo or usuario.rol != RolEnum.REPARTIDOR:
        raise UnprocessableError(
            "El repartidor no existe, está dado de baja o no tiene el rol Repartidor.",
            code="repartidor_invalido",
        )
    return usuario


def _armar_entregas(db: Session, fecha: date, paradas: list[ParadaIn]) -> list[Entrega]:
    """Valida las paradas y arma las entregas con los precios vigentes (se congelan al confirmar)."""
    puntos_ids = [p.punto_entrega_id for p in paradas]
    if len(puntos_ids) != len(set(puntos_ids)):
        raise UnprocessableError("Hay puntos de entrega repetidos en la hoja.", code="punto_repetido")

    puntos = {p.id: p for p in db.scalars(select(PuntoEntrega).where(PuntoEntrega.id.in_(puntos_ids)))}
    faltantes = sorted(set(puntos_ids) - set(puntos))
    if faltantes:
        raise NotFoundError(f"Punto(s) de entrega inexistente(s): {faltantes}.", details={"ids": faltantes})
    inactivos = [p.nombre for p in puntos.values() if not p.activo]
    if inactivos:
        raise ConflictError(f"Punto(s) de entrega dado(s) de baja: {', '.join(inactivos)}.")

    por_parada = [stock.agrupar((i.producto_id, i.cantidad) for i in p.items) for p in paradas]
    producto_ids = {pid for cantidades in por_parada for pid in cantidades}
    productos = {p.id: p for p in db.scalars(select(Producto).where(Producto.id.in_(producto_ids)))}
    faltantes = sorted(producto_ids - set(productos))
    if faltantes:
        raise NotFoundError(f"Producto(s) inexistente(s): {faltantes}.", details={"ids": faltantes})
    bajas = [p.nombre for p in productos.values() if not p.activo]
    if bajas:
        raise ConflictError(f"Producto(s) dado(s) de baja: {', '.join(sorted(bajas))}.")

    entregas = []
    for parada, cantidades in zip(paradas, por_parada, strict=True):
        precios = descuentos.resolver_precios(db, parada.punto_entrega_id, cantidades, fecha)
        entrega = Entrega(punto_entrega_id=parada.punto_entrega_id, orden_sugerido=0)
        for pid, cantidad in cantidades.items():
            precio = precios[pid]
            entrega.items.append(
                EntregaItem(
                    producto_id=pid, cantidad_planificada=cantidad, precio_lista=precio.precio_lista,
                    descuento_pct=precio.descuento_pct, precio_unitario=precio.precio_unitario,
                )
            )
        entregas.append(entrega)
    return entregas


def _ordenar(db: Session, hoja: HojaRuta) -> None:
    """Calcula el orden sugerido y la distancia estimada (§5.1). Es solo una sugerencia."""
    db.flush()
    entregas = _query_hoja_entregas(db, hoja.id)
    settings = get_settings()
    origen = None
    if settings.panaderia_latitud is not None and settings.panaderia_longitud is not None:
        origen = (float(settings.panaderia_latitud), float(settings.panaderia_longitud))
    paradas = [
        rutas.Parada(
            id=e.id,
            latitud=float(e.punto.latitud) if e.punto.latitud is not None else None,
            longitud=float(e.punto.longitud) if e.punto.longitud is not None else None,
            cierre=e.punto.ventana_hasta,
        )
        for e in entregas
    ]
    orden, km = rutas.ordenar_ruta(paradas, origen)
    posicion = {entrega_id: i + 1 for i, entrega_id in enumerate(orden)}
    for e in entregas:
        e.orden_sugerido = posicion[e.id]
    hoja.distancia_sugerida_km = Decimal(str(km)).quantize(DOS_DECIMALES)
    db.flush()


def _query_hoja_entregas(db: Session, hoja_id: int) -> list[Entrega]:
    return list(
        db.scalars(
            select(Entrega)
            .where(Entrega.hoja_id == hoja_id)
            .order_by(Entrega.id)
            .options(selectinload(Entrega.punto))
            .execution_options(populate_existing=True)
        )
    )


def crear_hoja(db: Session, usuario: Usuario, datos: HojaRutaCreate) -> HojaRutaOut:
    _validar_repartidor(db, datos.repartidor_id)
    hoja = HojaRuta(fecha=datos.fecha, repartidor_id=datos.repartidor_id, creado_por_id=usuario.id)
    hoja.entregas = _armar_entregas(db, datos.fecha, datos.paradas)
    db.add(hoja)
    _ordenar(db, hoja)
    db.commit()
    return ver_hoja(db, hoja.id)


def editar_hoja(db: Session, hoja_id: int, datos: HojaRutaUpdate) -> HojaRutaOut:
    hoja = _bloquear_hoja(db, hoja_id)
    if hoja.estado != H.BORRADOR:
        raise ConflictError(
            "Solo se puede editar una hoja en borrador (reabrila para cambiarla).",
            code="transicion_invalida",
        )
    cambios = datos.model_dump(exclude_unset=True)
    if cambios.get("repartidor_id") is not None:
        _validar_repartidor(db, cambios["repartidor_id"])
        hoja.repartidor_id = cambios["repartidor_id"]
    if cambios.get("fecha") is not None:
        hoja.fecha = cambios["fecha"]
    if cambios.get("paradas") is not None:
        nuevas = _armar_entregas(db, hoja.fecha, datos.paradas)
        _bloquear_entregas(db, hoja.id)
        hoja.entregas.clear()
        db.flush()
        hoja.entregas.extend(nuevas)
    _ordenar(db, hoja)
    db.commit()
    return ver_hoja(db, hoja_id)


def generar_desde_plantillas(db: Session, usuario: Usuario, fecha: date) -> GeneracionOut:
    """Crea borradores con el pedido fijo de cada punto para el día de la semana de `fecha`.

    Un borrador por repartidor habitual. Los puntos que no se pueden incluir se informan en
    `omitidos`; volver a generar no duplica nada (los puntos ya presentes se omiten).
    """
    dia = fecha.weekday()
    puntos = db.scalars(
        select(PuntoEntrega)
        .join(PlantillaEntrega, PlantillaEntrega.punto_entrega_id == PuntoEntrega.id)
        .where(PuntoEntrega.activo.is_(True), PlantillaEntrega.dia_semana == dia)
        .options(selectinload(PuntoEntrega.plantillas).selectinload(PlantillaEntrega.producto))
        .distinct()
        .order_by(PuntoEntrega.nombre)
    ).all()

    ya_en_hoja = set(
        db.scalars(
            select(Entrega.punto_entrega_id)
            .join(HojaRuta, HojaRuta.id == Entrega.hoja_id)
            .where(HojaRuta.fecha == fecha, HojaRuta.estado != H.ANULADA)
        )
    )
    repartidores_validos = {
        u.id
        for u in db.scalars(
            select(Usuario).where(Usuario.activo.is_(True), Usuario.rol == RolEnum.REPARTIDOR)
        )
    }

    omitidos: list[OmitidoOut] = []
    por_repartidor: dict[int, list[ParadaIn]] = defaultdict(list)
    for p in puntos:
        if p.id in ya_en_hoja:
            omitidos.append(OmitidoOut(punto=p.nombre, motivo="Ya está en una hoja de ese día."))
            continue
        if p.repartidor_habitual_id is None:
            omitidos.append(OmitidoOut(punto=p.nombre, motivo="No tiene repartidor habitual."))
            continue
        if p.repartidor_habitual_id not in repartidores_validos:
            omitidos.append(OmitidoOut(punto=p.nombre, motivo="Su repartidor habitual no está activo."))
            continue
        items = [
            ItemHojaIn(producto_id=pl.producto_id, cantidad=pl.cantidad)
            for pl in p.plantillas
            if pl.dia_semana == dia and pl.producto.activo
        ]
        if not items:
            omitidos.append(
                OmitidoOut(punto=p.nombre, motivo="Los productos de su plantilla están dados de baja.")
            )
            continue
        por_repartidor[p.repartidor_habitual_id].append(ParadaIn(punto_entrega_id=p.id, items=items))

    hojas = []
    for repartidor_id, paradas in sorted(por_repartidor.items()):
        hoja = HojaRuta(fecha=fecha, repartidor_id=repartidor_id, creado_por_id=usuario.id)
        hoja.entregas = _armar_entregas(db, fecha, paradas)
        db.add(hoja)
        _ordenar(db, hoja)
        hojas.append(hoja)
    db.commit()
    return GeneracionOut(hojas=[_resumen(_obtener_hoja(db, h.id)) for h in hojas], omitidos=omitidos)


def recalcular_ruta(db: Session, hoja_id: int) -> HojaRutaOut:
    hoja = _bloquear_hoja(db, hoja_id)
    if hoja.estado not in (H.BORRADOR, H.CONFIRMADA):
        raise _transicion_invalida(hoja, "recalcular la ruta de")
    _bloquear_entregas(db, hoja.id)
    _ordenar(db, hoja)
    db.commit()
    return ver_hoja(db, hoja_id)


# ---------- Confirmar, reabrir, anular ----------


def confirmar_hoja(db: Session, hoja_id: int) -> HojaRutaOut:
    """Congela los precios y reserva el stock: desde acá la caja no puede vender esa mercadería."""
    hoja = _bloquear_hoja(db, hoja_id)
    if hoja.estado != H.BORRADOR:
        raise _transicion_invalida(hoja, "confirmar")
    entregas = _bloquear_entregas(db, hoja.id)
    if not entregas:
        raise UnprocessableError("La hoja no tiene paradas.", code="hoja_vacia")

    a_reservar: dict[int, int] = defaultdict(int)
    for entrega in entregas:
        precios = descuentos.resolver_precios(
            db, entrega.punto_entrega_id, [i.producto_id for i in entrega.items], hoja.fecha
        )
        for item in entrega.items:
            precio = precios[item.producto_id]
            item.precio_lista = precio.precio_lista
            item.descuento_pct = precio.descuento_pct
            item.precio_unitario = precio.precio_unitario
            a_reservar[item.producto_id] += item.cantidad_planificada

    productos = stock.bloquear_productos(db, a_reservar.keys())
    stock.reservar_productos(productos, a_reservar)

    hoja.items.clear()
    db.flush()
    for pid, cantidad in sorted(a_reservar.items()):
        hoja.items.append(HojaRutaItem(producto_id=pid, cantidad_reservada=cantidad))
    hoja.estado = H.CONFIRMADA
    hoja.confirmada_en = utcnow()
    _ordenar(db, hoja)
    db.commit()
    return ver_hoja(db, hoja_id)


def _liberar(db: Session, hoja: HojaRuta) -> None:
    reservado = {i.producto_id: i.cantidad_reservada for i in _items_hoja(db, hoja.id)}
    if reservado:
        productos = stock.bloquear_productos(db, reservado.keys(), solo_activos=False)
        stock.liberar_reserva(productos, reservado)
    hoja.items.clear()
    db.flush()


def reabrir_hoja(db: Session, hoja_id: int) -> HojaRutaOut:
    hoja = _bloquear_hoja(db, hoja_id)
    if hoja.estado != H.CONFIRMADA:
        raise _transicion_invalida(hoja, "reabrir")
    _bloquear_entregas(db, hoja.id)
    _liberar(db, hoja)
    hoja.estado = H.BORRADOR
    hoja.confirmada_en = None
    db.commit()
    return ver_hoja(db, hoja_id)


def anular_hoja(db: Session, hoja_id: int) -> HojaRutaOut:
    hoja = _bloquear_hoja(db, hoja_id)
    if hoja.estado not in (H.BORRADOR, H.CONFIRMADA):
        raise _transicion_invalida(hoja, "anular")
    _bloquear_entregas(db, hoja.id)
    if hoja.estado == H.CONFIRMADA:
        _liberar(db, hoja)
    hoja.estado = H.ANULADA
    db.commit()
    return ver_hoja(db, hoja_id)


# ---------- Carga del vehículo ----------


def cargar_hoja(db: Session, usuario: Usuario, hoja_id: int, datos: CargaIn) -> HojaRutaOut:
    """El stock sale del local y se abre el turno de reparto del repartidor.

    Sin `items`, se carga todo lo reservado. Con `items`, solo lo indicado: lo reservado que no se
    cargó queda disponible para la caja en el mismo instante.
    """
    hoja = _bloquear_hoja(db, hoja_id)
    if usuario.rol == RolEnum.REPARTIDOR:
        _exigir_repartidor(hoja.repartidor_id, usuario)
    if hoja.estado != H.CONFIRMADA:
        raise _transicion_invalida(hoja, "cargar")

    items = _items_hoja(db, hoja.id)
    reservado = {i.producto_id: i.cantidad_reservada for i in items}
    if datos.items:
        cargado = stock.agrupar((i.producto_id, i.cantidad) for i in datos.items)
        ajenos = sorted(set(cargado) - set(reservado))
        if ajenos:
            raise UnprocessableError(
                f"Producto(s) que no están en la hoja: {ajenos}.", code="producto_fuera_de_hoja",
                details={"ids": ajenos},
            )
    else:
        cargado = dict(reservado)
    cargado = {pid: cantidad for pid, cantidad in cargado.items() if cantidad > 0}
    if not cargado:
        raise UnprocessableError("No se cargó ninguna unidad.", code="carga_vacia")

    repartidor = db.get(Usuario, hoja.repartidor_id)
    if caja.turno_abierto(db, repartidor, TipoTurnoEnum.REPARTO) is not None:
        raise ConflictError(
            "El repartidor ya tiene una hoja de ruta cargada sin rendir.", code="turno_ya_abierto"
        )

    productos = stock.bloquear_productos(db, reservado.keys(), solo_activos=False)
    stock.cargar_reserva(productos, reservado, cargado)
    for item in items:
        item.cantidad_cargada = cargado.get(item.producto_id, 0)

    turno = Turno(
        usuario_id=hoja.repartidor_id, tipo=TipoTurnoEnum.REPARTO, efectivo_inicial=datos.fondo_inicial
    )
    db.add(turno)
    db.flush()
    hoja.turno_id = turno.id
    hoja.estado = H.CARGADA
    hoja.cargada_en = utcnow()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError(
            "El repartidor ya tiene una hoja de ruta cargada sin rendir.", code="turno_ya_abierto"
        ) from None
    return ver_hoja(db, hoja_id)


def _guardar_punto_inicial(db: Session, hoja_id: int, op: InicioRutaIn) -> None:
    if op.posicion is None:
        return
    insertar_nuevos(
        db, RecorridoPunto.__table__,
        {"lote_id": op.operacion_id, "registrado_en_dispositivo": op.posicion.registrado_en,
         "hoja_id": hoja_id, "latitud": op.posicion.latitud, "longitud": op.posicion.longitud,
         "precision_m": op.posicion.precision_m, "recibido_en_servidor": utcnow()},
    )


def iniciar_ruta(db: Session, usuario: Usuario, hoja_id: int, datos: InicioRutaIn) -> dict:
    """CARGADA → EN_RUTA. Sin permiso de ubicación no se sale: el recorrido es obligatorio (D18)."""

    def accion() -> HojaRutaOut:
        hoja = _bloquear_hoja(db, hoja_id)
        _exigir_repartidor(hoja.repartidor_id, usuario)
        if hoja.estado in CERRADAS:
            raise _hoja_cerrada()
        if hoja.estado == H.EN_RUTA:
            return ver_hoja(db, hoja_id)  # ya había salido (otra operación): no hay nada que hacer
        if hoja.estado != H.CARGADA:
            raise _transicion_invalida(hoja, "iniciar la ruta de")
        if not datos.ubicacion_concedida:
            raise ConflictError(
                "Para salir a la ruta tenés que permitir el acceso a la ubicación del dispositivo.",
                code="hoja_sin_ubicacion",
            )
        hoja.estado = H.EN_RUTA
        hoja.iniciada_en = utcnow()
        _guardar_punto_inicial(db, hoja.id, datos)
        db.flush()
        return ver_hoja(db, hoja_id)

    return _operar(db, usuario, datos.operacion_id, f"inicio_ruta:{hoja_id}", accion)


# ---------- Entregas (app del repartidor) ----------


def _bloquear_entrega(
    db: Session, usuario: Usuario, entrega_id: int, *, cobra: bool
) -> tuple[HojaRuta, Entrega]:
    """Toma los bloqueos de una operación sobre una entrega: turno (share, si cobra) → hoja → entrega.

    Se lee primero sin bloquear solo para saber a qué turno y hoja pertenece: todo lo que se
    decide se vuelve a verificar con las filas bloqueadas.
    """
    ref = db.execute(
        select(Entrega.hoja_id, HojaRuta.turno_id, HojaRuta.repartidor_id, HojaRuta.estado)
        .join(HojaRuta, HojaRuta.id == Entrega.hoja_id)
        .where(Entrega.id == entrega_id)
    ).first()
    if ref is None:
        raise NotFoundError("Entrega no encontrada.")
    if ref.repartidor_id != usuario.id:
        raise ForbiddenError("Esta entrega no es de tu hoja de ruta.")
    if ref.estado in CERRADAS:
        raise _hoja_cerrada()

    if cobra and ref.turno_id is not None:
        try:
            turnos.bloquear_para_cobro(db, ref.turno_id)  # nivel 2
        except ConflictError as e:
            if e.code == "turno_cerrado":
                raise _hoja_cerrada() from None
            raise

    # El FOR UPDATE de la hoja (y no un FOR SHARE) hace consistente `orden_real`: dos entregas
    # confirmándose a la vez no pueden leer el mismo "siguiente número".
    hoja = _bloquear_hoja(db, ref.hoja_id)  # nivel 3
    if hoja.estado in CERRADAS:
        raise _hoja_cerrada()
    if hoja.estado != H.EN_RUTA:
        raise ConflictError(
            "Primero tenés que iniciar la ruta para registrar entregas.", code="transicion_invalida"
        )
    entrega = db.scalar(  # nivel 4
        _query_entrega().where(Entrega.id == entrega_id).with_for_update(key_share=True)
    )
    return hoja, entrega


def _siguiente_orden(db: Session, hoja_id: int) -> int:
    return (db.scalar(select(func.max(Entrega.orden_real)).where(Entrega.hoja_id == hoja_id)) or 0) + 1


def _siguiente_remito(db: Session) -> int:
    """Nivel 6. Numeración sin huecos: el contador se incrementa bajo bloqueo y en la misma
    transacción que la entrega, así un rollback no deja números salteados."""
    insertar_nuevos(db, Numerador.__table__, {"tipo": "remito", "ultimo_numero": 0})
    numerador = db.scalar(
        select(Numerador)
        .where(Numerador.tipo == "remito")
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    numerador.ultimo_numero += 1
    return numerador.ultimo_numero


def _registrar_evento(
    entrega: Entrega, tipo: TipoEventoEntregaEnum, usuario: Usuario, posicion: PosicionIn | None,
    detalle: str | None = None,
) -> None:
    entrega.eventos.append(
        EntregaEvento(
            tipo=tipo, usuario_id=usuario.id, detalle=detalle,
            latitud=posicion.latitud if posicion else None,
            longitud=posicion.longitud if posicion else None,
            precision_m=posicion.precision_m if posicion else None,
            registrado_en_dispositivo=posicion.registrado_en if posicion else None,
        )
    )


def _fijar_posicion(entrega: Entrega, op: OperacionMovil) -> None:
    ahora = utcnow()
    entrega.recibida_en_servidor = ahora
    if op.posicion is not None:
        entrega.latitud = op.posicion.latitud
        entrega.longitud = op.posicion.longitud
        entrega.confirmada_en_dispositivo = op.posicion.registrado_en
    else:
        entrega.confirmada_en_dispositivo = op.registrado_en


def check_in(db: Session, usuario: Usuario, entrega_id: int, datos: OperacionMovil) -> dict:
    def accion() -> EntregaOut:
        _, entrega = _bloquear_entrega(db, usuario, entrega_id, cobra=False)
        if entrega.estado not in ABIERTAS:
            raise ConflictError("La entrega ya fue resuelta.", code="entrega_cerrada")
        if entrega.estado == E.PENDIENTE:
            entrega.estado = E.EN_LOCAL
            _registrar_evento(entrega, TipoEventoEntregaEnum.CHECK_IN, usuario, datos.posicion)
        db.flush()
        return _entrega_out_por_id(db, entrega_id)

    return _operar(db, usuario, datos.operacion_id, f"check_in:{entrega_id}", accion)


def no_entregada(db: Session, usuario: Usuario, entrega_id: int, datos: NoEntregadaIn) -> dict:
    def accion() -> EntregaOut:
        hoja, entrega = _bloquear_entrega(db, usuario, entrega_id, cobra=False)
        if entrega.estado not in ABIERTAS:
            raise ConflictError("La entrega ya fue resuelta.", code="entrega_cerrada")
        entrega.estado = E.NO_ENTREGADA
        entrega.motivo_no_entrega = datos.motivo
        entrega.operacion_id = datos.operacion_id
        entrega.orden_real = _siguiente_orden(db, hoja.id)
        _fijar_posicion(entrega, datos)
        _registrar_evento(entrega, TipoEventoEntregaEnum.NO_ENTREGADA, usuario, datos.posicion, datos.motivo)
        db.flush()
        return _entrega_out_por_id(db, entrega_id)

    return _operar(db, usuario, datos.operacion_id, f"no_entregada:{entrega_id}", accion)


def _subtotal(precio: Decimal, cantidad: int) -> Decimal:
    return stock.redondear_dinero(Decimal(precio) * cantidad)


def confirmar_entrega(db: Session, usuario: Usuario, entrega_id: int, datos: ConfirmacionEntregaIn) -> dict:
    """Entrega (total o parcial) con su venta, remito, cobro y saldo de cuenta corriente.

    El stock no se toca: ya salió del local en la carga. Los importes salen de los precios
    congelados al confirmar la hoja; el dispositivo solo informa cantidades y lo que cobró.
    """

    def accion() -> EntregaOut:
        hoja, entrega = _bloquear_entrega(db, usuario, entrega_id, cobra=True)
        if entrega.estado not in ABIERTAS:
            raise ConflictError("La entrega ya fue resuelta.", code="entrega_cerrada")

        planificados = {i.producto_id: i for i in entrega.items}
        entregadas: dict[int, int] = {}
        for linea in datos.items:
            item = planificados.get(linea.producto_id)
            if item is None:
                raise UnprocessableError(
                    f"El producto {linea.producto_id} no es parte de esta entrega.",
                    code="producto_fuera_de_entrega",
                )
            if linea.cantidad_entregada > item.cantidad_planificada:
                raise UnprocessableError(
                    f"No se puede entregar más de lo planificado de {item.producto.nombre}.",
                    code="cantidad_excede_planificada",
                )
            entregadas[linea.producto_id] = linea.cantidad_entregada
        entregadas = {pid: c for pid, c in entregadas.items() if c > 0}
        if not entregadas:
            raise UnprocessableError(
                "No se entregó ninguna unidad: registrala como no entregada.", code="entrega_vacia"
            )

        # Lo entregado en toda la hoja no puede superar lo que se cargó en el vehículo
        ya_entregado = dict(
            db.execute(
                select(EntregaItem.producto_id, func.sum(EntregaItem.cantidad_entregada))
                .join(Entrega, Entrega.id == EntregaItem.entrega_id)
                .where(Entrega.hoja_id == hoja.id, Entrega.id != entrega.id)
                .group_by(EntregaItem.producto_id)
            ).all()
        )
        cargado = {i.producto_id: i.cantidad_cargada for i in _items_hoja(db, hoja.id)}
        excedidos = [
            {
                "producto_id": pid, "nombre": planificados[pid].producto.nombre,
                "cargado": cargado.get(pid, 0), "ya_entregado": int(ya_entregado.get(pid, 0)),
                "solicitado": cantidad,
            }
            for pid, cantidad in entregadas.items()
            if int(ya_entregado.get(pid, 0)) + cantidad > cargado.get(pid, 0)
        ]
        if excedidos:
            raise ConflictError(
                "Se quiere entregar más de lo que hay cargado en el vehículo.",
                code="cantidad_excede_carga", details=excedidos,
            )

        total = sum((_subtotal(planificados[pid].precio_unitario, c) for pid, c in entregadas.items()), CERO)
        cobrado = sum((p.monto for p in datos.pagos), CERO)
        if cobrado > total:
            raise UnprocessableError(
                f"Lo cobrado ({cobrado}) supera el total de la entrega ({total}).",
                code="pago_excede_total", details={"total": float(total), "cobrado": float(cobrado)},
            )
        caja.validar_medios([p.metodo_pago for p in datos.pagos])
        a_cuenta = total - cobrado

        punto = entrega.punto
        cliente = (
            contabilidad.bloquear_cliente(db, punto.cliente_id)  # nivel 5
            if a_cuenta > 0
            else db.get(Cliente, punto.cliente_id)
        )
        if cliente is None:
            raise NotFoundError("Cliente no encontrado.")
        remito = _siguiente_remito(db)  # nivel 6

        pagos = [(p.metodo_pago, p.monto, p.referencia) for p in datos.pagos]
        if a_cuenta > 0:
            pagos.append((MetodoPagoEnum.CUENTA_CORRIENTE, a_cuenta, None))
        venta = Venta(
            turno_id=hoja.turno_id, usuario_id=usuario.id, cliente_id=cliente.id,
            origen=OrigenVentaEnum.REPARTO, punto_entrega_id=punto.id, monto=total,
            metodo_pago=max(pagos, key=lambda p: p[1])[0],
        )
        for pid, cantidad in entregadas.items():
            precio = Decimal(planificados[pid].precio_unitario)
            venta.detalles.append(
                DetalleVenta(
                    producto_id=pid, cantidad=cantidad, precio_unitario=precio,
                    subtotal=_subtotal(precio, cantidad),
                )
            )
        for metodo, monto, referencia in pagos:
            venta.pagos.append(
                VentaPago(
                    metodo_pago=metodo, monto=monto, referencia=referencia, estado=EstadoPagoEnum.APROBADO
                )
            )
        db.add(venta)
        db.flush()
        if a_cuenta > 0:
            contabilidad.registrar_cargo_venta(
                db, cliente, venta, a_cuenta, usuario, punto_entrega_id=punto.id
            )

        for item in entrega.items:
            item.cantidad_entregada = entregadas.get(item.producto_id, 0)
        completa = all(i.cantidad_entregada == i.cantidad_planificada for i in entrega.items)
        entrega.estado = E.ENTREGADA if completa else E.PARCIAL
        entrega.venta_id = venta.id
        entrega.numero_remito = remito
        entrega.operacion_id = datos.operacion_id
        entrega.orden_real = _siguiente_orden(db, hoja.id)
        entrega.recibio_nombre = datos.recibio_nombre
        _fijar_posicion(entrega, datos)
        _registrar_evento(entrega, TipoEventoEntregaEnum.CONFIRMADA, usuario, datos.posicion)
        db.flush()
        return _entrega_out_por_id(db, entrega_id)

    return _operar(db, usuario, datos.operacion_id, f"confirmacion:{entrega_id}", accion)


# ---------- Recorrido GPS ----------


def guardar_recorrido(db: Session, usuario: Usuario, hoja_id: int, lote: RecorridoLoteIn) -> dict:
    """Guarda un lote de puntos. Solo agregado: no bloquea nada mientras la hoja está en ruta.

    Un lote que llega después de la rendición (sincronización tardía) se guarda igual y
    actualiza la distancia real de la hoja.
    """
    ref = db.execute(select(HojaRuta.repartidor_id, HojaRuta.estado).where(HojaRuta.id == hoja_id)).first()
    if ref is None:
        raise NotFoundError("Hoja de ruta no encontrada.")
    _exigir_repartidor(ref.repartidor_id, usuario)
    if ref.estado == H.EN_RUTA:
        return recorrido.guardar_lote(db, hoja_id, lote)
    if ref.estado != H.RENDIDA:
        if ref.estado == H.ANULADA:
            raise _hoja_cerrada()
        raise ConflictError("La hoja todavía no salió a la ruta.", code="transicion_invalida")

    hoja = _bloquear_hoja(db, hoja_id)
    resultado = recorrido.guardar_lote(db, hoja_id, lote, commit=False)
    db.flush()
    hoja.distancia_real_km = recorrido.distancia_real_km(db, hoja_id)
    db.commit()
    return resultado


# ---------- Rendición ----------


def rendir_hoja(db: Session, usuario: Usuario, hoja_id: int, datos: RendicionIn) -> HojaRutaOut:
    """Cierra la hoja: devoluciones al stock o a merma, y arqueo ciego del efectivo del reparto.

    Todo en una transacción. Lo que no se visitó se cierra como no entregado.
    """
    ref = db.execute(select(HojaRuta.turno_id, HojaRuta.estado).where(HojaRuta.id == hoja_id)).first()
    if ref is None:
        raise NotFoundError("Hoja de ruta no encontrada.")
    if ref.estado in CERRADAS:
        raise _hoja_cerrada()
    if ref.turno_id is None:
        raise ConflictError(
            f"No se puede rendir una hoja en estado '{ref.estado.value}': todavía no se cargó.",
            code="transicion_invalida",
        )

    # Nivel 2: el FOR UPDATE espera a que terminen las entregas en curso (que tienen el turno FOR SHARE)
    turno = db.scalar(
        select(Turno)
        .where(Turno.id == ref.turno_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    hoja = _bloquear_hoja(db, hoja_id)
    if hoja.estado in CERRADAS or turno.estado == EstadoTurnoEnum.CERRADO:
        raise _hoja_cerrada()
    if hoja.estado not in (H.CARGADA, H.EN_RUTA):
        raise _transicion_invalida(hoja, "rendir")

    entregas = _bloquear_entregas(db, hoja.id)
    for entrega in entregas:
        if entrega.estado in ABIERTAS:
            entrega.estado = E.NO_ENTREGADA
            entrega.motivo_no_entrega = "No se visitó"
            entrega.recibida_en_servidor = utcnow()
            _registrar_evento(entrega, TipoEventoEntregaEnum.NO_ENTREGADA, usuario, None, "Cerrada al rendir")
    db.flush()

    items = _items_hoja(db, hoja.id)
    entregado = dict(
        db.execute(
            select(EntregaItem.producto_id, func.sum(EntregaItem.cantidad_entregada))
            .join(Entrega, Entrega.id == EntregaItem.entrega_id)
            .where(Entrega.hoja_id == hoja.id)
            .group_by(EntregaItem.producto_id)
        ).all()
    )
    esperado = {i.producto_id: i.cantidad_cargada - int(entregado.get(i.producto_id, 0)) for i in items}

    declarado: dict[int, int] = defaultdict(int)
    por_destino: dict[DestinoDevolucionEnum, dict[int, int]] = {
        d: defaultdict(int) for d in DestinoDevolucionEnum
    }
    for d in datos.devoluciones:
        if d.producto_id not in esperado:
            raise UnprocessableError(
                f"El producto {d.producto_id} no está en la hoja.", code="producto_fuera_de_hoja"
            )
        declarado[d.producto_id] += d.cantidad
        por_destino[d.destino][d.producto_id] += d.cantidad
    nombres = {i.producto_id: i.producto.nombre for i in items}
    diferencias = [
        {
            "producto_id": pid, "nombre": nombres[pid], "esperado": esperado[pid],
            "declarado": declarado.get(pid, 0),
        }
        for pid in esperado
        if esperado[pid] != declarado.get(pid, 0)
    ]
    if diferencias:
        raise UnprocessableError(
            "Las devoluciones no coinciden con lo que quedó sin entregar.",
            code="devolucion_no_cuadra", details=diferencias,
        )

    reingreso = por_destino[DestinoDevolucionEnum.REINGRESO]
    if reingreso:
        destino = stock.destinos_de_reingreso(db, reingreso.keys())
        a_reingresar: dict[int, int] = defaultdict(int)
        for pid, cantidad in reingreso.items():
            a_reingresar[destino[pid]] += cantidad
        productos = stock.bloquear_productos(db, a_reingresar.keys(), solo_activos=False)  # nivel 7
        stock.reingresar_devolucion(productos, a_reingresar)
    for pid, cantidad in sorted(por_destino[DestinoDevolucionEnum.MERMA].items()):
        db.add(
            Merma(
                producto_id=pid, usuario_id=usuario.id, cantidad_perdida=cantidad, motivo=MOTIVO_DEVOLUCION
            )
        )
    for item in items:
        item.cantidad_devuelta = declarado.get(item.producto_id, 0)

    db.flush()
    hoja.distancia_real_km = recorrido.distancia_real_km(db, hoja.id)
    hoja.estado = H.RENDIDA
    hoja.rendida_en = utcnow()
    # Arqueo ciego del efectivo del reparto: no se devuelve la diferencia
    caja.cerrar_turno(db, ref.turno_id, datos.efectivo_declarado, commit=False, permitir_reparto=True)
    db.commit()
    return ver_hoja(db, hoja_id)


# ---------- Lectura ----------


def _cobrado(db: Session, venta_ids: list[int]) -> dict[int, Decimal]:
    if not venta_ids:
        return {}
    return {
        venta_id: Decimal(total)
        for venta_id, total in db.execute(
            select(VentaPago.venta_id, func.sum(VentaPago.monto))
            .where(
                VentaPago.venta_id.in_(venta_ids),
                VentaPago.estado == EstadoPagoEnum.APROBADO,
                VentaPago.metodo_pago != MetodoPagoEnum.CUENTA_CORRIENTE,
            )
            .group_by(VentaPago.venta_id)
        )
    }


def _total_entrega(entrega: Entrega) -> Decimal:
    """Planificado mientras la entrega está abierta; lo entregado de verdad una vez resuelta."""
    resuelta = entrega.estado not in ABIERTAS
    return sum(
        (
            _subtotal(i.precio_unitario, i.cantidad_entregada if resuelta else i.cantidad_planificada)
            for i in entrega.items
        ),
        CERO,
    )


def _entrega_out(entrega: Entrega, cobrado: Decimal) -> EntregaOut:
    punto = entrega.punto
    resuelta = entrega.estado not in ABIERTAS
    return EntregaOut(
        id=entrega.id, hoja_id=entrega.hoja_id, punto_entrega_id=punto.id, punto_nombre=punto.nombre,
        cliente_id=punto.cliente_id, cliente_nombre=punto.cliente.nombre, direccion=punto.direccion,
        latitud=punto.latitud, longitud=punto.longitud,
        ventana_desde=punto.ventana_desde, ventana_hasta=punto.ventana_hasta,
        contacto=punto.contacto, notas=punto.notas,
        orden_sugerido=entrega.orden_sugerido, orden_real=entrega.orden_real, estado=entrega.estado,
        numero_remito=entrega.numero_remito, motivo_no_entrega=entrega.motivo_no_entrega,
        total=_total_entrega(entrega), cobrado=cobrado,
        saldo_cliente=Decimal(punto.cliente.saldo_cuenta_corriente),
        items=[
            ItemEntregaOut(
                producto_id=i.producto_id, nombre=i.producto.nombre,
                cantidad_planificada=i.cantidad_planificada, cantidad_entregada=i.cantidad_entregada,
                precio_lista=i.precio_lista, descuento_pct=i.descuento_pct, precio_unitario=i.precio_unitario,
                subtotal=_subtotal(
                    i.precio_unitario, i.cantidad_entregada if resuelta else i.cantidad_planificada
                ),
            )
            for i in entrega.items
        ],
    )


def _entrega_out_por_id(db: Session, entrega_id: int) -> EntregaOut:
    entrega = db.scalar(_query_entrega().where(Entrega.id == entrega_id))
    cobrado = _cobrado(db, [entrega.venta_id] if entrega.venta_id else [])
    return _entrega_out(entrega, cobrado.get(entrega.venta_id, CERO))


def _total_planificado(hoja: HojaRuta) -> Decimal:
    return sum(
        (_subtotal(i.precio_unitario, i.cantidad_planificada) for e in hoja.entregas for i in e.items), CERO
    )


def _hoja_out(db: Session, hoja: HojaRuta) -> HojaRutaOut:
    cobrado = _cobrado(db, [e.venta_id for e in hoja.entregas if e.venta_id])
    entregado: dict[int, int] = defaultdict(int)
    for e in hoja.entregas:
        for i in e.items:
            entregado[i.producto_id] += i.cantidad_entregada
    return HojaRutaOut(
        id=hoja.id, fecha=hoja.fecha, estado=hoja.estado, repartidor_id=hoja.repartidor_id,
        repartidor=hoja.repartidor.nombre or hoja.repartidor.username, turno_id=hoja.turno_id,
        total_planificado=_total_planificado(hoja),
        distancia_sugerida_km=hoja.distancia_sugerida_km, distancia_real_km=hoja.distancia_real_km,
        confirmada_en=hoja.confirmada_en, cargada_en=hoja.cargada_en,
        iniciada_en=hoja.iniciada_en, rendida_en=hoja.rendida_en,
        entregas=[_entrega_out(e, cobrado.get(e.venta_id, CERO)) for e in hoja.entregas],
        carga=[
            CargaItemOut(
                producto_id=i.producto_id, nombre=i.producto.nombre, reservada=i.cantidad_reservada,
                cargada=i.cantidad_cargada, entregada=entregado.get(i.producto_id, 0),
                devuelta=i.cantidad_devuelta,
            )
            for i in hoja.items
        ],
    )


def _resumen(hoja: HojaRuta) -> HojaRutaResumenOut:
    resueltas = sum(1 for e in hoja.entregas if e.estado not in ABIERTAS)
    return HojaRutaResumenOut(
        id=hoja.id, fecha=hoja.fecha, estado=hoja.estado, repartidor_id=hoja.repartidor_id,
        repartidor=hoja.repartidor.nombre or hoja.repartidor.username, paradas=len(hoja.entregas),
        entregadas=resueltas, pendientes=len(hoja.entregas) - resueltas,
        total_planificado=_total_planificado(hoja), distancia_sugerida_km=hoja.distancia_sugerida_km,
    )


def ver_hoja(db: Session, hoja_id: int) -> HojaRutaOut:
    return _hoja_out(db, _obtener_hoja(db, hoja_id))


def obtener_recorrido(db: Session, hoja_id: int) -> dict:
    return recorrido.obtener_recorrido(db, _obtener_hoja(db, hoja_id))


def listar_hojas(db: Session, fecha: date | None = None) -> list[HojaRutaResumenOut]:
    fecha = fecha or stock.hoy_local()
    hojas = db.scalars(
        _query_hoja().where(HojaRuta.fecha == fecha).order_by(HojaRuta.id)
    ).all()
    return [_resumen(h) for h in hojas]


_PRIORIDAD_HOY = {H.EN_RUTA: 0, H.CARGADA: 1, H.CONFIRMADA: 2, H.RENDIDA: 3}


def hoja_de_hoy(db: Session, usuario: Usuario) -> HojaRutaOut:
    """La hoja del repartidor para guardar en el dispositivo: la que está en ruta o cargada
    (aunque sea de un día anterior que no se rindió) o, si no, la de hoy."""
    hoy = stock.hoy_local()
    hojas = db.scalars(
        _query_hoja().where(
            HojaRuta.repartidor_id == usuario.id,
            HojaRuta.estado.in_(tuple(_PRIORIDAD_HOY)),
            (HojaRuta.fecha == hoy) | HojaRuta.estado.in_((H.CARGADA, H.EN_RUTA)),
        )
    ).all()
    if not hojas:
        raise NotFoundError("No tenés una hoja de ruta para hoy.", code="sin_hoja")
    elegida = min(hojas, key=lambda h: (_PRIORIDAD_HOY[h.estado], -h.id))
    return _hoja_out(db, elegida)


def resumen_del_dia(db: Session, fecha: date) -> ResumenEntregasOut:
    hojas = db.scalars(_query_hoja().where(HojaRuta.fecha == fecha, HojaRuta.estado != H.ANULADA)).all()
    entregas = [e for h in hojas for e in h.entregas]
    ventas = [e.venta_id for e in entregas if e.venta_id]
    facturacion = a_cuenta = CERO
    cobrado = CERO
    if ventas:
        facturacion = Decimal(
            db.scalar(select(func.coalesce(func.sum(Venta.monto), 0)).where(Venta.id.in_(ventas)))
        )
        cobrado = sum(_cobrado(db, ventas).values(), CERO)
        a_cuenta = facturacion - cobrado
    return ResumenEntregasOut(
        fecha=fecha, hojas=len(hojas), paradas=len(entregas),
        completadas=sum(1 for e in entregas if e.estado == E.ENTREGADA),
        parciales=sum(1 for e in entregas if e.estado == E.PARCIAL),
        no_entregadas=sum(1 for e in entregas if e.estado == E.NO_ENTREGADA),
        pendientes=sum(1 for e in entregas if e.estado in ABIERTAS),
        facturacion_reparto=facturacion, cobrado=cobrado, a_cuenta_corriente=a_cuenta,
    )


def exigir_cliente_en_ruta(db: Session, usuario: Usuario, cliente_id: int) -> None:
    """El repartidor solo cobra deuda a clientes que tiene en su hoja de ruta cargada o en ruta."""
    visita = db.scalar(
        select(Entrega.id)
        .join(HojaRuta, HojaRuta.id == Entrega.hoja_id)
        .join(PuntoEntrega, PuntoEntrega.id == Entrega.punto_entrega_id)
        .where(
            HojaRuta.repartidor_id == usuario.id,
            HojaRuta.estado.in_((H.CARGADA, H.EN_RUTA)),
            PuntoEntrega.cliente_id == cliente_id,
        )
        .limit(1)
    )
    if visita is None:
        raise ForbiddenError("Solo podés cobrar a clientes de tu hoja de ruta en curso.")


def listar_repartidores(db: Session) -> list[Usuario]:
    return list(
        db.scalars(
            select(Usuario)
            .where(Usuario.activo.is_(True), Usuario.rol == RolEnum.REPARTIDOR)
            .order_by(Usuario.nombre, Usuario.username)
        )
    )
