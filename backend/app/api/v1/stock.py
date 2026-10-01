from fastapi import APIRouter, status

from app.api.deps import DB, Gestion
from app.schemas.inventario import DiaAnteriorIn, DiaAnteriorOut
from app.services import inventario, stock

router = APIRouter(prefix="/stock", tags=["Stock"])


@router.get("/dia-anterior", response_model=DiaAnteriorOut)
def ver_dia_anterior(_: Gestion, db: DB):
    """Productos que tienen variante de día anterior y las conversiones de hoy."""
    return inventario.listar_dia_anterior(db)


@router.post("/dia-anterior", response_model=DiaAnteriorOut, status_code=status.HTTP_201_CREATED)
def pasar_a_dia_anterior(datos: DiaAnteriorIn, usuario: Gestion, db: DB):
    """Ajuste manual de la encargada: mueve unidades del producto fresco a su variante.

    Todo o nada. No toca el stock reservado para el reparto.
    """
    stock.pasar_a_dia_anterior(
        db, usuario, [(i.producto_id, i.cantidad) for i in datos.items], datos.motivo
    )
    return inventario.listar_dia_anterior(db)


@router.post("/dia-anterior/{conversion_id}/reversion", response_model=DiaAnteriorOut)
def revertir_conversion(conversion_id: int, usuario: Gestion, db: DB):
    """Deshace una conversión del mismo día, siempre que la variante conserve ese stock."""
    stock.revertir_conversion(db, usuario, conversion_id)
    return inventario.listar_dia_anterior(db)
