from datetime import date

from fastapi import APIRouter, status

from app.api.deps import DB, Interno, Produccion
from app.schemas.comercial import PendienteProduccion
from app.schemas.inventario import MermaCreate, MermaOut, ProduccionIn, ProduccionOut
from app.services import finanzas, pedidos
from app.services import inventario as svc

router = APIRouter(tags=["Producción"])


@router.post("/produccion", response_model=ProduccionOut, status_code=status.HTTP_201_CREATED)
def registrar_produccion(datos: ProduccionIn, usuario: Produccion, db: DB):
    """Registra lotes: suma stock de producto y descuenta insumos según receta."""
    lotes, consumo, insumos = svc.registrar_produccion(
        db, usuario, [(lote.producto_id, lote.cantidad) for lote in datos.lotes]
    )
    return {
        "lotes": lotes,
        "unidades_totales": sum(lote.cantidad_producida for lote in lotes),
        "insumos_consumidos": [
            {"materia_prima_id": mp_id, "nombre": insumos[mp_id].nombre,
             "cantidad": cant, "unidad_medida": insumos[mp_id].unidad_medida}
            for mp_id, cant in consumo.items()
        ],
    }


@router.get("/produccion/pendiente", response_model=list[PendienteProduccion])
def pendiente_por_pedidos(_: Produccion, db: DB, desde: date | None = None, hasta: date | None = None):
    """Unidades comprometidas en pedidos no entregados, frente al stock actual."""
    ini = finanzas.rango_local(desde, desde)[0] if desde else None
    fin = finanzas.rango_local(hasta, hasta)[1] if hasta else None
    return pedidos.pendientes_produccion(db, ini, fin)


@router.post("/mermas", response_model=MermaOut, status_code=status.HTTP_201_CREATED)
def registrar_merma(datos: MermaCreate, usuario: Interno, db: DB):
    # Cualquier rol del local puede informar una merma (caída, vencido, quemado...). Las del
    # reparto se informan en la rendición, no desde acá.
    return svc.registrar_merma(db, usuario, datos.producto_id, datos.cantidad_perdida, datos.motivo)
