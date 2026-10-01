from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ConflictError, NotFoundError
from app.models import (
    ConversionDiaAnterior,
    LoteProduccion,
    MateriaPrima,
    Merma,
    Producto,
    RecetaInsumo,
    Usuario,
)
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


def _validar_codigo(db: Session, codigo: str | None, excepto_id: int | None = None) -> None:
    if codigo is None:
        return
    q = select(Producto.id).where(Producto.codigo == codigo)
    if excepto_id is not None:
        q = q.where(Producto.id != excepto_id)
    if db.scalar(q) is not None:
        raise ConflictError(f"Ya existe un producto con el código {codigo}.", code="codigo_duplicado")


def _validar_variante(db: Session, producto_base_id: int | None, producto_id: int | None = None) -> None:
    """Una variante "día anterior" apunta a un producto fresco, y hay una sola por producto."""
    if producto_base_id is None:
        return
    if producto_base_id == producto_id:
        raise ConflictError("Un producto no puede ser variante de sí mismo.", code="variante_invalida")
    base = db.get(Producto, producto_base_id)
    if base is None:
        raise NotFoundError("El producto base no existe.")
    if base.producto_base_id is not None:
        raise ConflictError(
            "El producto base ya es una variante: no se encadenan variantes.", code="variante_invalida"
        )
    q = select(Producto.id).where(Producto.producto_base_id == producto_base_id)
    if producto_id is not None:
        q = q.where(Producto.id != producto_id)
        if db.scalar(select(Producto.id).where(Producto.producto_base_id == producto_id)) is not None:
            raise ConflictError(
                "Este producto ya tiene su propia variante: no puede ser variante de otro.",
                code="variante_invalida",
            )
    if db.scalar(q) is not None:
        raise ConflictError(
            "Ese producto ya tiene una variante de día anterior.", code="variante_duplicada"
        )


def _confirmar(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        # Carrera entre dos altas con el mismo código o la misma variante
        db.rollback()
        raise ConflictError("El código o la variante ya están en uso.", code="codigo_duplicado") from None


def crear_producto(db: Session, datos: ProductoCreate) -> Producto:
    _validar_codigo(db, datos.codigo)
    _validar_variante(db, datos.producto_base_id)
    producto = Producto(**datos.model_dump())
    db.add(producto)
    _confirmar(db)
    return producto


def actualizar_producto(db: Session, producto_id: int, datos: ProductoUpdate) -> Producto:
    producto = obtener_producto(db, producto_id)
    cambios = datos.model_dump(exclude_unset=True)
    if "codigo" in cambios:
        _validar_codigo(db, cambios["codigo"], excepto_id=producto_id)
    if "producto_base_id" in cambios:
        _validar_variante(db, cambios["producto_base_id"], producto_id=producto_id)
    # Estos campos admiten null para limpiarlos; el resto ignora null
    anulables = {"categoria", "codigo", "producto_base_id"}
    for campo, valor in cambios.items():
        if valor is not None or campo in anulables:
            setattr(producto, campo, valor)
    _confirmar(db)
    return producto


def ajustar_stock_producto(db: Session, producto_id: int, nuevo_stock: int) -> Producto:
    producto = stock.bloquear_productos(db, [producto_id], solo_activos=False)[producto_id]
    if nuevo_stock < producto.stock_reservado:
        raise ConflictError(
            f"No se puede dejar el stock en {nuevo_stock}: hay {producto.stock_reservado} "
            "unidades reservadas para el reparto.",
            code="stock_menor_a_reservado",
        )
    producto.stock_mostrador = nuevo_stock
    db.commit()
    return producto


# ---------- Pan del día anterior ----------


def listar_dia_anterior(db: Session) -> dict:
    """Productos con variante (para la pantalla "Pasar a día anterior") y las conversiones de hoy."""
    variantes = db.scalars(
        select(Producto).where(Producto.producto_base_id.is_not(None), Producto.activo.is_(True))
    ).all()
    bases = {
        b.id: b
        for b in db.scalars(
            select(Producto).where(
                Producto.id.in_([v.producto_base_id for v in variantes]), Producto.activo.is_(True)
            )
        )
    }
    productos = [
        {
            "producto_id": b.id, "nombre": b.nombre, "stock_mostrador": b.stock_mostrador,
            "stock_disponible": stock.disponible(b), "variante_id": v.id,
            "variante_nombre": v.nombre, "variante_stock": v.stock_mostrador,
            "variante_precio": v.precio_venta,
        }
        for v in variantes
        if (b := bases.get(v.producto_base_id)) is not None
    ]
    productos.sort(key=lambda p: p["nombre"])

    hoy = [
        c
        for c in db.scalars(
            select(ConversionDiaAnterior)
            .options(
                selectinload(ConversionDiaAnterior.producto_base),
                selectinload(ConversionDiaAnterior.variante),
            )
            .order_by(ConversionDiaAnterior.id.desc())
            .limit(200)
        )
        if stock.fecha_local(c.fecha) == stock.hoy_local()
    ]
    revertidas = {c.revierte_id for c in hoy if c.revierte_id is not None}
    usuarios = {
        u.id: u.username
        for u in db.scalars(select(Usuario).where(Usuario.id.in_({c.usuario_id for c in hoy})))
    }
    conversiones = [
        {
            "id": c.id, "producto_id": c.producto_base_id, "producto": c.producto_base.nombre,
            "variante_id": c.variante_id, "variante": c.variante.nombre, "cantidad": c.cantidad,
            "usuario": usuarios.get(c.usuario_id, "?"), "fecha": c.fecha, "motivo": c.motivo,
            "revierte_id": c.revierte_id, "revertida": c.id in revertidas,
            "se_puede_revertir": c.revierte_id is None and c.id not in revertidas,
        }
        for c in hoy
    ]
    return {"productos": productos, "conversiones_hoy": conversiones}


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
