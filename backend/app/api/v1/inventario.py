from decimal import Decimal

from fastapi import APIRouter, status

from app.api.deps import DB, CurrentUser, Gestion
from app.models import MateriaPrima, Producto, RecetaInsumo, RolEnum
from app.schemas.inventario import (
    AjusteStockProducto,
    MateriaPrimaCreate,
    MateriaPrimaOut,
    MateriaPrimaUpdate,
    ProductoCreate,
    ProductoOut,
    ProductoUpdate,
    RecetaIn,
    RecetaOut,
)
from app.services import inventario as svc
from app.services.stock import redondear_dinero

router = APIRouter(tags=["Inventario"])


def _receta_out(producto: Producto, insumos: list[RecetaInsumo]) -> dict:
    items = []
    for r in insumos:
        mp: MateriaPrima = r.materia_prima
        costo = Decimal(r.cantidad_necesaria) * Decimal(mp.costo_unitario_actual)
        items.append({
            "materia_prima_id": mp.id, "materia_prima": mp.nombre, "unidad_medida": mp.unidad_medida,
            "cantidad_necesaria": r.cantidad_necesaria, "costo": redondear_dinero(costo),
        })
    return {
        "producto_id": producto.id,
        "insumos": items,
        "costo_unitario": sum((i["costo"] for i in items), Decimal("0")),
    }


# ---------- Productos ----------


@router.get("/productos", response_model=list[ProductoOut])
def listar_productos(usuario: CurrentUser, db: DB, incluir_inactivos: bool = False):
    gestion = usuario.rol in (RolEnum.ADMIN, RolEnum.ENCARGADA)
    return svc.listar_productos(db, incluir_inactivos=incluir_inactivos and gestion)


@router.post("/productos", response_model=ProductoOut, status_code=status.HTTP_201_CREATED)
def crear_producto(datos: ProductoCreate, _: Gestion, db: DB):
    return svc.crear_producto(db, datos)


@router.patch("/productos/{producto_id}", response_model=ProductoOut)
def actualizar_producto(producto_id: int, datos: ProductoUpdate, _: Gestion, db: DB):
    return svc.actualizar_producto(db, producto_id, datos)


@router.put("/productos/{producto_id}/stock", response_model=ProductoOut)
def ajustar_stock(producto_id: int, datos: AjusteStockProducto, _: Gestion, db: DB):
    return svc.ajustar_stock_producto(db, producto_id, datos.stock_mostrador)


@router.get("/productos/{producto_id}/receta", response_model=RecetaOut)
def ver_receta(producto_id: int, _: CurrentUser, db: DB):
    return _receta_out(*svc.obtener_receta(db, producto_id))


@router.put("/productos/{producto_id}/receta", response_model=RecetaOut)
def reemplazar_receta(producto_id: int, datos: RecetaIn, _: Gestion, db: DB):
    return _receta_out(*svc.reemplazar_receta(db, producto_id, datos.insumos))


# ---------- Materias primas ----------


@router.get("/materias-primas", response_model=list[MateriaPrimaOut])
def listar_materias_primas(_: CurrentUser, db: DB):
    return svc.listar_materias_primas(db)


@router.post("/materias-primas", response_model=MateriaPrimaOut, status_code=status.HTTP_201_CREATED)
def crear_materia_prima(datos: MateriaPrimaCreate, _: Gestion, db: DB):
    return svc.crear_materia_prima(db, datos)


@router.patch("/materias-primas/{mp_id}", response_model=MateriaPrimaOut)
def actualizar_materia_prima(mp_id: int, datos: MateriaPrimaUpdate, _: Gestion, db: DB):
    return svc.actualizar_materia_prima(db, mp_id, datos)
