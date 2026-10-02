from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.models import (
    CompraMateriaPrima,
    DetalleVenta,
    EstadoPagoEnum,
    GastoVario,
    MateriaPrima,
    Merma,
    Producto,
    Proveedor,
    Venta,
    VentaPago,
)
from app.schemas.finanzas import CompraCreate, GastoCreate, ProveedorCreate
from app.services import stock

CERO = Decimal("0")


def zona() -> ZoneInfo:
    return ZoneInfo(get_settings().zona_horaria)


def hoy() -> date:
    return datetime.now(zona()).date()


def rango_local(desde: date, hasta: date) -> tuple[datetime, datetime]:
    """[desde 00:00, hasta+1 00:00) en hora local, como datetimes con tz."""
    tz = zona()
    return (
        datetime.combine(desde, time.min, tzinfo=tz),
        datetime.combine(hasta + timedelta(days=1), time.min, tzinfo=tz),
    )


# ---------- Proveedores ----------


def listar_proveedores(db: Session) -> list[Proveedor]:
    return list(db.scalars(select(Proveedor).order_by(Proveedor.nombre)))


def crear_proveedor(db: Session, datos: ProveedorCreate) -> Proveedor:
    proveedor = Proveedor(**datos.model_dump())
    db.add(proveedor)
    db.commit()
    return proveedor


def actualizar_proveedor(db: Session, proveedor_id: int, datos: ProveedorCreate) -> Proveedor:
    proveedor = db.get(Proveedor, proveedor_id)
    if proveedor is None:
        raise NotFoundError("Proveedor no encontrado.")
    for campo, valor in datos.model_dump().items():
        setattr(proveedor, campo, valor)
    db.commit()
    return proveedor


# ---------- Compras ----------


def registrar_compra(db: Session, datos: CompraCreate) -> CompraMateriaPrima:
    if db.get(Proveedor, datos.proveedor_id) is None:
        raise NotFoundError("Proveedor no encontrado.")
    insumos = stock.bloquear_materias_primas(db, [datos.materia_prima_id])
    mp = insumos.get(datos.materia_prima_id)
    if mp is None:
        raise NotFoundError("Materia prima no encontrada.")

    # Costo promedio ponderado: valoriza el stock existente al costo anterior
    # y el ingresado al costo de esta compra.
    stock_previo = max(Decimal(mp.stock_actual), CERO)
    valor_previo = stock_previo * Decimal(mp.costo_unitario_actual)
    nuevo_stock = stock_previo + datos.cantidad_comprada
    mp.costo_unitario_actual = ((valor_previo + datos.precio_total) / nuevo_stock).quantize(
        Decimal("0.0001")
    )
    mp.stock_actual = Decimal(mp.stock_actual) + datos.cantidad_comprada

    compra = CompraMateriaPrima(**datos.model_dump())
    db.add(compra)
    db.commit()
    return compra


def listar_compras(db: Session, limite: int = 100) -> list[CompraMateriaPrima]:
    return list(
        db.scalars(
            select(CompraMateriaPrima)
            .order_by(CompraMateriaPrima.fecha.desc())
            .limit(limite)
            .options(
                selectinload(CompraMateriaPrima.proveedor),
                selectinload(CompraMateriaPrima.materia_prima),
            )
        )
    )


# ---------- Gastos ----------


def registrar_gasto(db: Session, datos: GastoCreate) -> GastoVario:
    gasto = GastoVario(**datos.model_dump())
    db.add(gasto)
    db.commit()
    return gasto


def listar_gastos(db: Session, limite: int = 100) -> list[GastoVario]:
    return list(db.scalars(select(GastoVario).order_by(GastoVario.fecha.desc()).limit(limite)))


# ---------- Resumen ----------


def _suma(db: Session, columna, *filtros) -> Decimal:
    return Decimal(db.scalar(select(func.coalesce(func.sum(columna), 0)).where(*filtros)) or 0)


def resumen(db: Session, desde: date, hasta: date) -> dict:
    ini, fin = rango_local(desde, hasta)
    en_rango = (Venta.fecha >= ini, Venta.fecha < fin)

    ventas = db.execute(select(Venta.fecha, Venta.monto).where(*en_rango)).all()
    total_ventas = sum((Decimal(v.monto) for v in ventas), CERO)

    # Por medio de pago salen de los pagos: en un pago mixto cada medio suma su parte
    # y la venta cuenta una vez en cada medio que usó.
    por_medio: dict[str, list] = {
        m.value: [Decimal(total), int(cantidad)]
        for m, total, cantidad in db.execute(
            select(
                VentaPago.metodo_pago,
                func.sum(VentaPago.monto),
                func.count(func.distinct(VentaPago.venta_id)),
            )
            .join(Venta, Venta.id == VentaPago.venta_id)
            .where(*en_rango, VentaPago.estado == EstadoPagoEnum.APROBADO)
            .group_by(VentaPago.metodo_pago)
        )
    }

    por_canal = {
        origen.value: (Decimal(total), int(cantidad))
        for origen, total, cantidad in db.execute(
            select(Venta.origen, func.sum(Venta.monto), func.count(Venta.id))
            .where(*en_rango)
            .group_by(Venta.origen)
        )
    }

    por_dia: dict[date, Decimal] = defaultdict(lambda: CERO)
    tz = zona()
    for v in ventas:
        fecha = v.fecha if v.fecha.tzinfo else v.fecha.replace(tzinfo=ZoneInfo("UTC"))
        por_dia[fecha.astimezone(tz).date()] += Decimal(v.monto)

    dias = []
    d = desde
    while d <= hasta:
        dias.append({"fecha": d, "total": por_dia.get(d, CERO)})
        d += timedelta(days=1)

    top = db.execute(
        select(
            Producto.id,
            Producto.nombre,
            func.sum(DetalleVenta.cantidad).label("unidades"),
            func.sum(DetalleVenta.subtotal).label("total"),
        )
        .join(DetalleVenta, DetalleVenta.producto_id == Producto.id)
        .join(Venta, Venta.id == DetalleVenta.venta_id)
        .where(*en_rango)
        .group_by(Producto.id, Producto.nombre)
        .order_by(func.sum(DetalleVenta.subtotal).desc())
        .limit(10)
    ).all()

    compras = _suma(
        db, CompraMateriaPrima.precio_total,
        CompraMateriaPrima.fecha >= ini, CompraMateriaPrima.fecha < fin,
    )
    gastos = _suma(db, GastoVario.monto, GastoVario.fecha >= ini, GastoVario.fecha < fin)
    merma = db.execute(
        select(
            func.coalesce(func.sum(Merma.cantidad_perdida), 0),
            func.coalesce(func.sum(Merma.cantidad_perdida * Producto.precio_venta), 0),
        )
        .join(Producto, Producto.id == Merma.producto_id)
        .where(Merma.fecha_hora >= ini, Merma.fecha_hora < fin)
    ).one()

    cantidad = len(ventas)
    return {
        "desde": desde,
        "hasta": hasta,
        "ventas_totales": total_ventas,
        "cantidad_ventas": cantidad,
        "ticket_promedio": stock.redondear_dinero(total_ventas / cantidad) if cantidad else CERO,
        "compras_materias_primas": compras,
        "gastos_operativos": gastos,
        "resultado": total_ventas - compras - gastos,
        "unidades_merma": int(merma[0]),
        "merma_valorizada": Decimal(merma[1]),
        "ventas_por_medio": [
            {"metodo_pago": m, "total": t, "cantidad": c} for m, (t, c) in sorted(por_medio.items())
        ],
        "ventas_por_canal": [
            {"canal": canal, "total": total, "cantidad": cantidad}
            for canal, (total, cantidad) in sorted(por_canal.items())
        ],
        "ventas_diarias": dias,
        "top_productos": [
            {"producto_id": r.id, "nombre": r.nombre, "unidades": int(r.unidades), "total": Decimal(r.total)}
            for r in top
        ],
    }


def alertas_stock(db: Session) -> dict:
    productos = db.scalars(
        select(Producto).where(Producto.activo.is_(True), Producto.stock_mostrador <= Producto.stock_minimo)
    ).all()
    insumos = db.scalars(
        select(MateriaPrima).where(MateriaPrima.stock_actual <= MateriaPrima.stock_minimo)
    ).all()
    return {"productos": productos, "materias_primas": insumos}
