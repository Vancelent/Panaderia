"""Reparto matutino: hojas de ruta, entregas y recorrido (docs/rfc-001 §3.6).

Las operaciones de la app del repartidor (`check-in`, `confirmacion`, `no-entregada`,
`inicio-ruta` y `recorrido`) son idempotentes: se pueden reintentar con el mismo
`operacion_id` (o `lote_id`) sin duplicar nada.
"""

from datetime import date

from fastapi import APIRouter, status

from app.api.deps import DB, Gestion, GestionORepartidor, Repartidor
from app.schemas.entregas import (
    CargaIn,
    ConfirmacionEntregaIn,
    EntregaOut,
    GeneracionOut,
    HojaRutaCreate,
    HojaRutaOut,
    HojaRutaResumenOut,
    HojaRutaUpdate,
    InicioRutaIn,
    LoteOut,
    NoEntregadaIn,
    OperacionMovil,
    RecorridoLoteIn,
    RecorridoOut,
    RendicionIn,
    RepartidorOut,
    ResumenEntregasOut,
)
from app.services import entregas, finanzas

router = APIRouter(prefix="/entregas", tags=["Reparto"])


# ---------- Gestión: armado, confirmación y rendición de hojas ----------


@router.get("/repartidores", response_model=list[RepartidorOut])
def listar_repartidores(_: Gestion, db: DB):
    return entregas.listar_repartidores(db)


@router.get("/resumen", response_model=ResumenEntregasOut)
def resumen(_: Gestion, db: DB, fecha: date | None = None):
    return entregas.resumen_del_dia(db, fecha or finanzas.hoy())


@router.get("/hojas", response_model=list[HojaRutaResumenOut])
def listar_hojas(_: Gestion, db: DB, fecha: date | None = None):
    return entregas.listar_hojas(db, fecha or finanzas.hoy())


@router.post("/hojas", response_model=HojaRutaOut, status_code=status.HTTP_201_CREATED)
def crear_hoja(datos: HojaRutaCreate, usuario: Gestion, db: DB):
    return entregas.crear_hoja(db, usuario, datos)


@router.post("/hojas/generacion", response_model=GeneracionOut)
def generar_hojas(fecha: date, usuario: Gestion, db: DB):
    """Crea borradores desde las plantillas de los puntos de entrega (uno por repartidor)."""
    return entregas.generar_desde_plantillas(db, usuario, fecha)


# Va antes de /hojas/{hoja_id} para que "hoy" no se interprete como un id
@router.get("/hojas/hoy", response_model=HojaRutaOut)
def hoja_de_hoy(usuario: Repartidor, db: DB):
    """La hoja del repartidor, completa, para guardarla en el dispositivo."""
    return entregas.hoja_de_hoy(db, usuario)


@router.get("/hojas/{hoja_id}", response_model=HojaRutaOut)
def ver_hoja(hoja_id: int, _: Gestion, db: DB):
    return entregas.ver_hoja(db, hoja_id)


@router.patch("/hojas/{hoja_id}", response_model=HojaRutaOut)
def editar_hoja(hoja_id: int, datos: HojaRutaUpdate, _: Gestion, db: DB):
    return entregas.editar_hoja(db, hoja_id, datos)


@router.post("/hojas/{hoja_id}/ruta-sugerida", response_model=HojaRutaOut)
def recalcular_ruta(hoja_id: int, _: Gestion, db: DB):
    return entregas.recalcular_ruta(db, hoja_id)


@router.post("/hojas/{hoja_id}/confirmacion", response_model=HojaRutaOut)
def confirmar_hoja(hoja_id: int, _: Gestion, db: DB):
    """Congela precios y reserva el stock: la caja deja de poder venderlo."""
    return entregas.confirmar_hoja(db, hoja_id)


@router.post("/hojas/{hoja_id}/reapertura", response_model=HojaRutaOut)
def reabrir_hoja(hoja_id: int, _: Gestion, db: DB):
    return entregas.reabrir_hoja(db, hoja_id)


@router.post("/hojas/{hoja_id}/anulacion", response_model=HojaRutaOut)
def anular_hoja(hoja_id: int, _: Gestion, db: DB):
    return entregas.anular_hoja(db, hoja_id)


@router.post("/hojas/{hoja_id}/carga", response_model=HojaRutaOut)
def cargar_hoja(hoja_id: int, datos: CargaIn, usuario: GestionORepartidor, db: DB):
    """Descuenta el stock, libera lo reservado que no se cargó y abre el turno de reparto."""
    return entregas.cargar_hoja(db, usuario, hoja_id, datos)


@router.post("/hojas/{hoja_id}/rendicion", response_model=HojaRutaOut)
def rendir_hoja(hoja_id: int, datos: RendicionIn, usuario: Gestion, db: DB):
    """Devoluciones, efectivo declarado y arqueo ciego (la diferencia no se devuelve)."""
    return entregas.rendir_hoja(db, usuario, hoja_id, datos)


@router.get("/hojas/{hoja_id}/recorrido", response_model=RecorridoOut)
def ver_recorrido(hoja_id: int, _: Gestion, db: DB):
    """Ruta sugerida vs. recorrido real, para el mapa del dueño."""
    return entregas.obtener_recorrido(db, hoja_id)


# ---------- Repartidor: operaciones de la app (idempotentes) ----------


@router.post("/hojas/{hoja_id}/inicio-ruta", response_model=HojaRutaOut)
def iniciar_ruta(hoja_id: int, datos: InicioRutaIn, usuario: Repartidor, db: DB):
    """CARGADA → EN_RUTA. Rechaza con `hoja_sin_ubicacion` si no se concedió el permiso de ubicación."""
    return entregas.iniciar_ruta(db, usuario, hoja_id, datos)


@router.post("/hojas/{hoja_id}/recorrido", response_model=LoteOut)
def guardar_recorrido(hoja_id: int, datos: RecorridoLoteIn, usuario: Repartidor, db: DB):
    return entregas.guardar_recorrido(db, usuario, hoja_id, datos)


@router.post("/{entrega_id}/check-in", response_model=EntregaOut)
def check_in(entrega_id: int, datos: OperacionMovil, usuario: Repartidor, db: DB):
    return entregas.check_in(db, usuario, entrega_id, datos)


@router.post("/{entrega_id}/confirmacion", response_model=EntregaOut)
def confirmar_entrega(entrega_id: int, datos: ConfirmacionEntregaIn, usuario: Repartidor, db: DB):
    return entregas.confirmar_entrega(db, usuario, entrega_id, datos)


@router.post("/{entrega_id}/no-entregada", response_model=EntregaOut)
def no_entregada(entrega_id: int, datos: NoEntregadaIn, usuario: Repartidor, db: DB):
    return entregas.no_entregada(db, usuario, entrega_id, datos)
