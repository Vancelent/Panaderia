"""Descuentos por punto de entrega y cálculo del precio final.

Reglas (docs/rfc-001 §4.2):
1. Para cada producto se busca primero un descuento **del producto**; si no hay, el **general**
   del punto; si no hay ninguno, precio de lista. Los descuentos no se suman entre sí.
2. Si hay varios del mismo nivel vigentes, se toma el de mayor porcentaje (desempate: el más
   nuevo), así el resultado es siempre determinista.
3. El cálculo usa solo `Decimal`: precio_lista × (1 − porcentaje / 100), redondeado a centavos.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import NotFoundError, UnprocessableError
from app.models import DescuentoPunto, Producto, PuntoEntrega
from app.schemas.contabilidad import DescuentoCreate, DescuentoUpdate
from app.services import stock

CIEN = Decimal("100")


@dataclass(frozen=True)
class PrecioResuelto:
    producto_id: int
    precio_lista: Decimal
    descuento_pct: Decimal | None
    descuento_id: int | None
    precio_unitario: Decimal


def precio_con_descuento(precio_lista: Decimal, porcentaje: Decimal | None) -> Decimal:
    if not porcentaje:
        return stock.redondear_dinero(Decimal(precio_lista))
    return stock.redondear_dinero(Decimal(precio_lista) * (CIEN - Decimal(porcentaje)) / CIEN)


def _vigente(d: DescuentoPunto, fecha: date) -> bool:
    return (d.vigente_desde is None or d.vigente_desde <= fecha) and (
        d.vigente_hasta is None or d.vigente_hasta >= fecha
    )


def _mejor(candidatos: list[DescuentoPunto]) -> DescuentoPunto | None:
    return max(candidatos, key=lambda d: (Decimal(d.porcentaje), d.id), default=None)


def resolver_precios(
    db: Session, punto_id: int, producto_ids: Iterable[int], fecha: date
) -> dict[int, PrecioResuelto]:
    """Precio final de cada producto para un punto de entrega en una fecha."""
    ids = sorted(set(producto_ids))
    productos = {p.id: p for p in db.scalars(select(Producto).where(Producto.id.in_(ids)))}
    faltantes = [i for i in ids if i not in productos]
    if faltantes:
        raise NotFoundError(f"Producto(s) inexistente(s): {faltantes}.", details={"ids": faltantes})

    descuentos = [
        d
        for d in db.scalars(
            select(DescuentoPunto).where(
                DescuentoPunto.punto_entrega_id == punto_id,
                DescuentoPunto.activo.is_(True),
                or_(DescuentoPunto.producto_id.is_(None), DescuentoPunto.producto_id.in_(ids)),
            )
        )
        if _vigente(d, fecha)
    ]
    general = _mejor([d for d in descuentos if d.producto_id is None])

    resultado = {}
    for pid in ids:
        elegido = _mejor([d for d in descuentos if d.producto_id == pid]) or general
        pct = Decimal(elegido.porcentaje) if elegido else None
        lista = Decimal(productos[pid].precio_venta)
        resultado[pid] = PrecioResuelto(
            producto_id=pid,
            precio_lista=lista,
            descuento_pct=pct,
            descuento_id=elegido.id if elegido else None,
            precio_unitario=precio_con_descuento(lista, pct),
        )
    return resultado


# ---------- Alta y edición ----------


def _punto(db: Session, punto_id: int) -> PuntoEntrega:
    punto = db.get(PuntoEntrega, punto_id)
    if punto is None:
        raise NotFoundError("Punto de entrega no encontrado.")
    return punto


def _validar_vigencia(desde: date | None, hasta: date | None) -> None:
    if desde and hasta and hasta < desde:
        raise UnprocessableError("La vigencia 'hasta' no puede ser anterior a 'desde'.")


def listar_descuentos(db: Session, punto_id: int) -> list[DescuentoPunto]:
    _punto(db, punto_id)
    return list(
        db.scalars(
            select(DescuentoPunto)
            .where(DescuentoPunto.punto_entrega_id == punto_id)
            .options(selectinload(DescuentoPunto.producto))
            .order_by(DescuentoPunto.id)
        )
    )


def crear_descuento(db: Session, punto_id: int, datos: DescuentoCreate) -> DescuentoPunto:
    _punto(db, punto_id)
    if datos.producto_id is not None and db.get(Producto, datos.producto_id) is None:
        raise NotFoundError("Producto no encontrado.")
    _validar_vigencia(datos.vigente_desde, datos.vigente_hasta)
    descuento = DescuentoPunto(punto_entrega_id=punto_id, **datos.model_dump())
    db.add(descuento)
    db.commit()
    return _con_producto(db, descuento.id)


def actualizar_descuento(
    db: Session, punto_id: int, descuento_id: int, datos: DescuentoUpdate
) -> DescuentoPunto:
    descuento = _con_producto(db, descuento_id)
    if descuento.punto_entrega_id != punto_id:
        raise NotFoundError("Descuento no encontrado.")
    cambios = datos.model_dump(exclude_unset=True)
    for campo in ("porcentaje", "motivo", "activo"):
        if cambios.get(campo) is None:
            cambios.pop(campo, None)
    for campo, valor in cambios.items():
        setattr(descuento, campo, valor)
    _validar_vigencia(descuento.vigente_desde, descuento.vigente_hasta)
    db.commit()
    return descuento


def _con_producto(db: Session, descuento_id: int) -> DescuentoPunto:
    descuento = db.scalar(
        select(DescuentoPunto)
        .where(DescuentoPunto.id == descuento_id)
        .options(selectinload(DescuentoPunto.producto))
    )
    if descuento is None:
        raise NotFoundError("Descuento no encontrado.")
    return descuento
