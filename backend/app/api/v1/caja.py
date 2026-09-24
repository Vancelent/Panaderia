from fastapi import APIRouter, Query, status

from app.api.deps import DB, Gestion, Mostrador
from app.core.errors import NotFoundError
from app.models import Arqueo, Venta
from app.schemas.caja import (
    ArqueoOut,
    TurnoAbrir,
    TurnoCerrar,
    TurnoCierreOut,
    TurnoOut,
    VentaCreate,
    VentaOut,
)
from app.services import caja as svc

router = APIRouter(tags=["Caja"])


def _venta_out(v: Venta) -> dict:
    return {
        "id": v.id, "turno_id": v.turno_id, "fecha": v.fecha, "metodo_pago": v.metodo_pago,
        "monto": v.monto, "cliente_id": v.cliente_id,
        "detalles": [
            {"producto_id": d.producto_id, "nombre": d.producto.nombre, "cantidad": d.cantidad,
             "precio_unitario": d.precio_unitario, "subtotal": d.subtotal}
            for d in v.detalles
        ],
    }


def _arqueo_out(a: Arqueo) -> dict:
    t = a.turno
    return {
        "id": a.id, "turno_id": t.id, "usuario": t.usuario.username,
        "fecha_apertura": t.fecha_apertura, "fecha_cierre": t.fecha_cierre,
        "efectivo_inicial": t.efectivo_inicial, "ventas_efectivo": a.ventas_efectivo,
        "ventas_otros_medios": a.ventas_otros_medios, "monto_sistema": a.monto_sistema,
        "monto_declarado": a.monto_declarado, "diferencia": a.diferencia,
    }


# ---------- Turno propio ----------


@router.get("/turnos/actual", response_model=TurnoOut | None)
def turno_actual(usuario: Mostrador, db: DB):
    """Turno abierto del usuario, o null si no tiene."""
    return svc.turno_abierto(db, usuario)


@router.post("/turnos", response_model=TurnoOut, status_code=status.HTTP_201_CREATED)
def abrir_turno(datos: TurnoAbrir, usuario: Mostrador, db: DB):
    return svc.abrir_turno(db, usuario, datos.efectivo_inicial)


@router.post("/turnos/actual/cierre", response_model=TurnoCierreOut)
def cerrar_turno_propio(datos: TurnoCerrar, usuario: Mostrador, db: DB):
    turno = svc.turno_abierto(db, usuario)
    if turno is None:
        raise NotFoundError("No tenés un turno abierto.")
    svc.cerrar_turno(db, turno.id, datos.monto_declarado)
    return {"mensaje": "Turno cerrado. El arqueo quedó registrado.", "turno_id": turno.id}


@router.get("/turnos/actual/ventas", response_model=list[VentaOut])
def ventas_turno_actual(usuario: Mostrador, db: DB, limite: int = Query(20, ge=1, le=200)):
    turno = svc.turno_abierto(db, usuario)
    if turno is None:
        return []
    return [_venta_out(v) for v in svc.ventas_de_turno(db, turno.id, limite)]


# ---------- Gestión de turnos ----------


@router.get("/turnos/abiertos", response_model=list[TurnoOut])
def turnos_abiertos(_: Gestion, db: DB):
    return svc.listar_turnos_abiertos(db)


@router.post("/turnos/{turno_id}/cierre", response_model=TurnoCierreOut)
def cerrar_turno_ajeno(turno_id: int, datos: TurnoCerrar, _: Gestion, db: DB):
    svc.cerrar_turno(db, turno_id, datos.monto_declarado)
    return {"mensaje": "Turno cerrado. El arqueo quedó registrado.", "turno_id": turno_id}


@router.get("/arqueos", response_model=list[ArqueoOut])
def listar_arqueos(_: Gestion, db: DB, limite: int = Query(100, ge=1, le=500)):
    return [_arqueo_out(a) for a in svc.listar_arqueos(db, limite)]


# ---------- Ventas ----------


@router.post("/ventas", response_model=VentaOut, status_code=status.HTTP_201_CREATED)
def registrar_venta(datos: VentaCreate, usuario: Mostrador, db: DB):
    # El turno sale de la sesión, nunca del cuerpo de la petición.
    turno = svc.exigir_turno_abierto(db, usuario)
    venta = svc.crear_venta(
        db,
        usuario=usuario,
        turno=turno,
        items=[(i.producto_id, i.cantidad) for i in datos.items],
        metodo_pago=datos.metodo_pago,
        cliente_id=datos.cliente_id,
    )
    return _venta_out(svc.obtener_venta(db, venta.id))
