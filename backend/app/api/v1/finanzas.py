from datetime import date, timedelta

from fastapi import APIRouter, Query, status

from app.api.deps import DB, Gestion
from app.core.errors import AppError
from app.models import CompraMateriaPrima
from app.schemas.finanzas import (
    CompraCreate,
    CompraOut,
    GastoCreate,
    GastoOut,
    ProveedorCreate,
    ProveedorOut,
    ResumenFinanciero,
)
from app.schemas.inventario import MateriaPrimaOut, ProductoOut
from app.services import finanzas as svc

router = APIRouter(tags=["Finanzas y compras"])


def _compra_out(c: CompraMateriaPrima) -> dict:
    return {
        "id": c.id, "proveedor_id": c.proveedor_id, "proveedor": c.proveedor.nombre,
        "materia_prima_id": c.materia_prima_id, "materia_prima": c.materia_prima.nombre,
        "cantidad_comprada": c.cantidad_comprada, "precio_total": c.precio_total, "fecha": c.fecha,
    }


@router.get("/proveedores", response_model=list[ProveedorOut])
def listar_proveedores(_: Gestion, db: DB):
    return svc.listar_proveedores(db)


@router.post("/proveedores", response_model=ProveedorOut, status_code=status.HTTP_201_CREATED)
def crear_proveedor(datos: ProveedorCreate, _: Gestion, db: DB):
    return svc.crear_proveedor(db, datos)


@router.put("/proveedores/{proveedor_id}", response_model=ProveedorOut)
def actualizar_proveedor(proveedor_id: int, datos: ProveedorCreate, _: Gestion, db: DB):
    return svc.actualizar_proveedor(db, proveedor_id, datos)


@router.get("/compras", response_model=list[CompraOut])
def listar_compras(_: Gestion, db: DB, limite: int = Query(100, ge=1, le=500)):
    return [_compra_out(c) for c in svc.listar_compras(db, limite)]


@router.post("/compras", response_model=CompraOut, status_code=status.HTTP_201_CREATED)
def registrar_compra(datos: CompraCreate, _: Gestion, db: DB):
    compra = svc.registrar_compra(db, datos)
    db.refresh(compra, ["proveedor", "materia_prima"])
    return _compra_out(compra)


@router.get("/gastos", response_model=list[GastoOut])
def listar_gastos(_: Gestion, db: DB, limite: int = Query(100, ge=1, le=500)):
    return svc.listar_gastos(db, limite)


@router.post("/gastos", response_model=GastoOut, status_code=status.HTTP_201_CREATED)
def registrar_gasto(datos: GastoCreate, _: Gestion, db: DB):
    return svc.registrar_gasto(db, datos)


@router.get("/finanzas/resumen", response_model=ResumenFinanciero)
def resumen(_: Gestion, db: DB, desde: date | None = None, hasta: date | None = None):
    hasta = hasta or svc.hoy()
    desde = desde or hasta - timedelta(days=29)
    if desde > hasta:
        raise AppError("La fecha 'desde' no puede ser posterior a 'hasta'.")
    if (hasta - desde).days > 366:
        raise AppError("El rango máximo es de un año.")
    return svc.resumen(db, desde, hasta)


@router.get("/stock/alertas")
def alertas_stock(_: Gestion, db: DB) -> dict[str, list]:
    alertas = svc.alertas_stock(db)
    return {
        "productos": [ProductoOut.model_validate(p).model_dump(mode="json") for p in alertas["productos"]],
        "materias_primas": [
            MateriaPrimaOut.model_validate(m).model_dump(mode="json") for m in alertas["materias_primas"]
        ],
    }
