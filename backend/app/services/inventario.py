from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ConflictError, NotFoundError
from app.models import LoteProduccion, MateriaPrima, Merma, Producto, RecetaInsumo, Usuario
from app.schemas.inventario import (
    MateriaPrimaCreate,
    MateriaPrimaUpdate,
    ProductoCreate,
    ProductoUpdate,
    RecetaItemIn,
)
from app.services import stock

# ---------- Productos ----------


def listar_productos(db: Session, *, incluir_inactivos: bool = False) -> list[Producto]:
    q = select(Producto).order_by(Producto.categoria.nulls_last(), Producto.nombre)
    if not incluir_inactivos:
        q = q.where(Producto.activo.is_(True))
    return list(db.scalars(q))


def obtener_producto(db: Session, producto_id: int) -> Producto:
    producto = db.get(Producto, producto_id)
    if producto is None:
        raise NotFoundError("Producto no encontrado.")
    return producto


def crear_producto(db: Session, datos: ProductoCreate) -> Producto:
    producto = Producto(**datos.model_dump())
    db.add(producto)
    db.commit()
    return producto


def actualizar_producto(db: Session, producto_id: int, datos: ProductoUpdate) -> Producto:
    producto = obtener_producto(db, producto_id)
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        if valor is not None or campo == "categoria":
            setattr(producto, campo, valor)
    db.commit()
    return producto


def ajustar_stock_producto(db: Session, producto_id: int, nuevo_stock: int) -> Producto:
    producto = stock.bloquear_productos(db, [producto_id], solo_activos=False)[producto_id]
    producto.stock_mostrador = nuevo_stock
    db.commit()
    return producto


# ---------- Materias primas ----------


def listar_materias_primas(db: Session) -> list[MateriaPrima]:
    return list(db.scalars(select(MateriaPrima).order_by(MateriaPrima.nombre)))


def obtener_materia_prima(db: Session, mp_id: int) -> MateriaPrima:
    mp = db.get(MateriaPrima, mp_id)
    if mp is None:
        raise NotFoundError("Materia prima no encontrada.")
    return mp


def crear_materia_prima(db: Session, datos: MateriaPrimaCreate) -> MateriaPrima:
    mp = MateriaPrima(**datos.model_dump())
    db.add(mp)
    db.commit()
    return mp


def actualizar_materia_prima(db: Session, mp_id: int, datos: MateriaPrimaUpdate) -> MateriaPrima:
    mp = obtener_materia_prima(db, mp_id)
    for campo, valor in datos.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(mp, campo, valor)
    db.commit()
    return mp


# ---------- Recetas ----------


def obtener_receta(db: Session, producto_id: int) -> tuple[Producto, list[RecetaInsumo]]:
    producto = obtener_producto(db, producto_id)
    insumos = list(
        db.scalars(
            select(RecetaInsumo)
            .where(RecetaInsumo.producto_id == producto_id)
            .options(selectinload(RecetaInsumo.materia_prima))
            .order_by(RecetaInsumo.id)
        )
    )
    return producto, insumos


def reemplazar_receta(
    db: Session, producto_id: int, items: list[RecetaItemIn]
) -> tuple[Producto, list[RecetaInsumo]]:
    producto = obtener_producto(db, producto_id)
    ids = [i.materia_prima_id for i in items]
    if len(ids) != len(set(ids)):
        raise ConflictError("La receta tiene insumos repetidos.")
    existentes = set(db.scalars(select(MateriaPrima.id).where(MateriaPrima.id.in_(ids))))
    faltantes = sorted(set(ids) - existentes)
    if faltantes:
        raise NotFoundError(f"Materia(s) prima(s) inexistente(s): {faltantes}.")

    producto.receta.clear()
    db.flush()
    for item in items:
        producto.receta.append(
            RecetaInsumo(materia_prima_id=item.materia_prima_id, cantidad_necesaria=item.cantidad_necesaria)
        )
    db.commit()
    return obtener_receta(db, producto_id)


# ---------- Producción ----------


def registrar_produccion(
    db: Session, usuario: Usuario, lotes: list[tuple[int, int]]
) -> tuple[list[LoteProduccion], dict[int, Decimal], dict[int, MateriaPrima]]:
    """Suma stock de productos y descuenta los insumos según la receta.

    Todo en una transacción: si falta un insumo, no se registra ningún lote.
    """
    cantidades = stock.agrupar(lotes)
    productos = stock.bloquear_productos(db, cantidades.keys())

    recetas = list(
        db.scalars(select(RecetaInsumo).where(RecetaInsumo.producto_id.in_(cantidades.keys())))
    )
    consumo: dict[int, Decimal] = {}
    for r in recetas:
        consumo[r.materia_prima_id] = consumo.get(r.materia_prima_id, Decimal("0")) + (
            Decimal(r.cantidad_necesaria) * cantidades[r.producto_id]
        )

    insumos = stock.bloquear_materias_primas(db, consumo.keys())
    insuficientes = [
        {"materia_prima_id": mp_id, "nombre": insumos[mp_id].nombre,
         "requerido": float(req), "disponible": float(insumos[mp_id].stock_actual),
         "unidad": insumos[mp_id].unidad_medida}
        for mp_id, req in consumo.items()
        if Decimal(insumos[mp_id].stock_actual) < req
    ]
    if insuficientes:
        detalle = ", ".join(
            f"{i['nombre']} (requiere {i['requerido']:g} {i['unidad']}, hay {i['disponible']:g})"
            for i in insuficientes
        )
        raise ConflictError(
            f"Materia prima insuficiente: {detalle}.",
            code="insumo_insuficiente",
            details=insuficientes,
        )

    for mp_id, req in consumo.items():
        insumos[mp_id].stock_actual = Decimal(insumos[mp_id].stock_actual) - req

    registrados = []
    for pid, cant in cantidades.items():
        productos[pid].stock_mostrador += cant
        lote = LoteProduccion(producto_id=pid, usuario_id=usuario.id, cantidad_producida=cant)
        db.add(lote)
        registrados.append(lote)
    db.commit()
    return registrados, consumo, insumos


def registrar_merma(
    db: Session, usuario: Usuario, producto_id: int, cantidad: int, motivo: str
) -> Merma:
    productos = stock.bloquear_productos(db, [producto_id], solo_activos=False)
    stock.descontar_productos(productos, {producto_id: cantidad})
    merma = Merma(
        producto_id=producto_id, usuario_id=usuario.id, cantidad_perdida=cantidad, motivo=motivo
    )
    db.add(merma)
    db.commit()
    return merma
