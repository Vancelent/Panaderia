"""Operaciones de stock con bloqueo de filas (SELECT ... FOR UPDATE).

Los bloqueos se toman siempre ordenados por id para evitar deadlocks entre
transacciones concurrentes (dos cajas vendiendo a la vez, producción, etc.).

Todas las lecturas bajo bloqueo usan `populate_existing`: en READ COMMITTED, tras
obtener el FOR UPDATE la fila es la última versión confirmada, pero SQLAlchemy no
pisaría los atributos de un objeto que ya estuviera cargado en la sesión.
"""

from collections import Counter
from collections.abc import Iterable
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError
from app.db.base import utcnow
from app.models import ConversionDiaAnterior, MateriaPrima, Producto, Usuario


def agrupar(items: Iterable[tuple[int, int]]) -> dict[int, int]:
    """Suma cantidades de ítems repetidos: [(1, 2), (1, 3)] -> {1: 5}."""
    total: Counter[int] = Counter()
    for producto_id, cantidad in items:
        total[producto_id] += cantidad
    return dict(total)


def bloquear_productos(db: Session, ids: Iterable[int], *, solo_activos: bool = True) -> dict[int, Producto]:
    ids = sorted(set(ids))
    productos = {
        p.id: p
        for p in db.scalars(
            select(Producto)
            .where(Producto.id.in_(ids))
            .order_by(Producto.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    }
    faltantes = [i for i in ids if i not in productos]
    if faltantes:
        raise NotFoundError(f"Producto(s) inexistente(s): {faltantes}.", details={"ids": faltantes})
    if solo_activos:
        inactivos = [p.nombre for p in productos.values() if not p.activo]
        if inactivos:
            raise ConflictError(f"Producto(s) dado(s) de baja: {', '.join(inactivos)}.")
    return productos


def bloquear_materias_primas(db: Session, ids: Iterable[int]) -> dict[int, MateriaPrima]:
    ids = sorted(set(ids))
    return {
        mp.id: mp
        for mp in db.scalars(
            select(MateriaPrima)
            .where(MateriaPrima.id.in_(ids))
            .order_by(MateriaPrima.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    }


def disponible(producto: Producto) -> int:
    """Unidades que el mostrador puede vender: lo que hay menos lo reservado para reparto."""
    return producto.stock_mostrador - producto.stock_reservado


def _stock_insuficiente(faltan: list[dict]) -> ConflictError:
    detalle = ", ".join(
        f"{i['nombre']} (disponible {i['disponible']}, pedido {i['solicitado']})" for i in faltan
    )
    return ConflictError(f"Stock insuficiente: {detalle}.", code="stock_insuficiente", details=faltan)


def descontar_productos(productos: dict[int, Producto], cantidades: dict[int, int]) -> None:
    """Valida todo primero y descuenta después: o se descuenta todo, o nada.

    Se valida contra el disponible, así que nunca se consume mercadería reservada.
    """
    insuficientes = [
        {"producto_id": pid, "nombre": productos[pid].nombre,
         "disponible": disponible(productos[pid]), "solicitado": cant}
        for pid, cant in cantidades.items()
        if disponible(productos[pid]) < cant
    ]
    if insuficientes:
        raise _stock_insuficiente(insuficientes)
    for pid, cant in cantidades.items():
        productos[pid].stock_mostrador -= cant


def redondear_dinero(valor: Decimal) -> Decimal:
    return valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ---------- Reparto: reservar, cargar y reingresar ----------


def reservar_productos(productos: dict[int, Producto], cantidades: dict[int, int]) -> None:
    """Compromete stock para una hoja de ruta confirmada. Valida todo antes de tocar nada.

    El CHECK de la base (0 <= reservado <= stock_mostrador) es la última defensa.
    """
    insuficientes = [
        {"producto_id": pid, "nombre": productos[pid].nombre,
         "disponible": disponible(productos[pid]), "solicitado": cant}
        for pid, cant in cantidades.items()
        if disponible(productos[pid]) < cant
    ]
    if insuficientes:
        raise _stock_insuficiente(insuficientes)
    for pid, cant in cantidades.items():
        productos[pid].stock_reservado += cant


def liberar_reserva(productos: dict[int, Producto], cantidades: dict[int, int]) -> None:
    """Devuelve a la caja lo reservado (hoja reabierta o anulada)."""
    for pid, cant in cantidades.items():
        if productos[pid].stock_reservado < cant:
            raise ConflictError(
                f"La reserva de {productos[pid].nombre} es menor a la que se quiere liberar.",
                code="reserva_inconsistente",
            )
    for pid, cant in cantidades.items():
        productos[pid].stock_reservado -= cant


def cargar_reserva(
    productos: dict[int, Producto], reservado: dict[int, int], cargado: dict[int, int]
) -> None:
    """La mercadería sale del local: baja el stock por lo cargado y se libera toda la reserva.

    Si se cargó menos de lo reservado, la diferencia queda disponible para la caja.
    """
    for pid, cant in cargado.items():
        if cant > reservado.get(pid, 0):
            raise ConflictError(
                f"No se puede cargar más de lo reservado de {productos[pid].nombre}.",
                code="cantidad_excede_reserva",
            )
    for pid, cant in reservado.items():
        productos[pid].stock_mostrador -= cargado.get(pid, 0)
        productos[pid].stock_reservado -= cant


def destinos_de_reingreso(db: Session, producto_ids: Iterable[int]) -> dict[int, int]:
    """producto -> producto que recibe lo que vuelve: su variante "día anterior" si la tiene."""
    ids = set(producto_ids)
    variante_de = {
        base: variante
        for base, variante in db.execute(
            select(Producto.producto_base_id, Producto.id).where(Producto.producto_base_id.in_(ids))
        )
    }
    return {pid: variante_de.get(pid, pid) for pid in ids}


def reingresar_devolucion(productos: dict[int, Producto], cantidades: dict[int, int]) -> None:
    """Suma al mostrador lo que volvió del reparto en condiciones de venderse."""
    for pid, cant in cantidades.items():
        productos[pid].stock_mostrador += cant


# ---------- Pan del día anterior ----------


def hoy_local() -> date:
    return datetime.now(ZoneInfo(get_settings().zona_horaria)).date()


def fecha_local(dt: datetime) -> date:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(ZoneInfo(get_settings().zona_horaria)).date()


def pasar_a_dia_anterior(
    db: Session, usuario: Usuario, pares: Iterable[tuple[int, int]], motivo: str | None = None
) -> list[ConversionDiaAnterior]:
    """Ajuste manual: mueve unidades de cada producto fresco a su variante "día anterior".

    Todo o nada, en una transacción. Bloquea en un solo `bloquear_productos()` los
    productos base y sus variantes, ordenados por id (nivel 7 de la jerarquía de
    bloqueos), y valida contra el disponible: no toca lo reservado.
    """
    cantidades = agrupar(pares)
    if not cantidades:
        raise ConflictError("No hay nada para pasar a día anterior.", code="sin_cantidades")

    # Mapa base -> variante leído SIN cargar entidades (no contamina la sesión) para saber
    # qué filas bloquear; después se confirma sobre las filas ya bloqueadas.
    filas = db.execute(
        select(Producto.producto_base_id, Producto.id).where(Producto.producto_base_id.in_(cantidades))
    ).all()
    variante_de = {base: variante for base, variante in filas}
    productos = bloquear_productos(db, [*cantidades, *variante_de.values()])

    sin_variante = [productos[b].nombre for b in cantidades if b not in variante_de]
    if sin_variante:
        raise ConflictError(
            f"Sin variante de día anterior: {', '.join(sin_variante)}.", code="sin_variante"
        )
    es_variante = [productos[b].nombre for b in cantidades if productos[b].producto_base_id is not None]
    if es_variante:
        raise ConflictError(
            f"Ya es una variante de día anterior: {', '.join(es_variante)}.", code="es_variante"
        )

    insuficientes = [
        {"producto_id": b, "nombre": productos[b].nombre,
         "disponible": disponible(productos[b]), "solicitado": c}
        for b, c in cantidades.items()
        if disponible(productos[b]) < c
    ]
    if insuficientes:
        raise _stock_insuficiente(insuficientes)

    conversiones = []
    for base, cant in sorted(cantidades.items()):
        productos[base].stock_mostrador -= cant
        productos[variante_de[base]].stock_mostrador += cant
        conversion = ConversionDiaAnterior(
            producto_base_id=base, variante_id=variante_de[base], cantidad=cant,
            usuario_id=usuario.id, motivo=motivo,
        )
        db.add(conversion)
        conversiones.append(conversion)
    db.commit()
    return conversiones


def revertir_conversion(db: Session, usuario: Usuario, conversion_id: int) -> ConversionDiaAnterior:
    """Deshace una conversión: solo el mismo día y solo con lo que siga disponible en la variante."""
    original = db.scalar(
        select(ConversionDiaAnterior)
        .where(ConversionDiaAnterior.id == conversion_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if original is None:
        raise NotFoundError("Conversión no encontrada.")
    if original.revierte_id is not None:
        raise ConflictError("Una reversión no se puede revertir.", code="conversion_no_revertible")
    if fecha_local(original.fecha) != hoy_local():
        raise ConflictError(
            "Solo se puede deshacer una conversión del mismo día.", code="conversion_vencida"
        )
    ya_revertida = db.scalar(
        select(ConversionDiaAnterior.id).where(ConversionDiaAnterior.revierte_id == original.id)
    )
    if ya_revertida is not None:
        raise ConflictError("La conversión ya fue revertida.", code="conversion_ya_revertida")

    productos = bloquear_productos(db, [original.producto_base_id, original.variante_id])
    variante = productos[original.variante_id]
    if disponible(variante) < original.cantidad:
        raise _stock_insuficiente([
            {"producto_id": variante.id, "nombre": variante.nombre,
             "disponible": disponible(variante), "solicitado": original.cantidad}
        ])
    variante.stock_mostrador -= original.cantidad
    productos[original.producto_base_id].stock_mostrador += original.cantidad
    reversion = ConversionDiaAnterior(
        producto_base_id=original.producto_base_id, variante_id=original.variante_id,
        cantidad=original.cantidad, usuario_id=usuario.id, revierte_id=original.id,
        motivo=f"Reversión de #{original.id}", fecha=utcnow(),
    )
    db.add(reversion)
    db.commit()
    return reversion
