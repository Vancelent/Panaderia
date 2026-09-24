"""Operaciones de stock con bloqueo de filas (SELECT ... FOR UPDATE).

Los bloqueos se toman siempre ordenados por id para evitar deadlocks entre
transacciones concurrentes (dos cajas vendiendo a la vez, producción, etc.).
"""

from collections import Counter
from collections.abc import Iterable
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models import MateriaPrima, Producto


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
            select(Producto).where(Producto.id.in_(ids)).order_by(Producto.id).with_for_update()
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
        )
    }


def descontar_productos(productos: dict[int, Producto], cantidades: dict[int, int]) -> None:
    """Valida todo primero y descuenta después: o se descuenta todo, o nada."""
    insuficientes = [
        {"producto_id": pid, "nombre": productos[pid].nombre,
         "disponible": productos[pid].stock_mostrador, "solicitado": cant}
        for pid, cant in cantidades.items()
        if productos[pid].stock_mostrador < cant
    ]
    if insuficientes:
        detalle = ", ".join(
            f"{i['nombre']} (disponible {i['disponible']}, pedido {i['solicitado']})"
            for i in insuficientes
        )
        raise ConflictError(
            f"Stock insuficiente: {detalle}.", code="stock_insuficiente", details=insuficientes
        )
    for pid, cant in cantidades.items():
        productos[pid].stock_mostrador -= cant


def redondear_dinero(valor: Decimal) -> Decimal:
    return valor.quantize(Decimal("0.01"))
