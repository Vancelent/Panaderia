from datetime import date

from fastapi import APIRouter, Query, status

from app.api.deps import DB, Gestion, GestionFuerte, GestionORepartidor
from app.models import DescuentoPunto, MovimientoCuentaCorriente, PuntoEntrega
from app.models.enums import MetodoPagoEnum, RolEnum, TipoTurnoEnum
from app.schemas.contabilidad import (
    AjusteIn,
    CuentaCorrienteOut,
    DescuentoCreate,
    DescuentoOut,
    DescuentoUpdate,
    MovimientoOut,
    NotaCreditoIn,
    PagoCuentaCorrienteIn,
    PlantillaDiaOut,
    PlantillasIn,
    PuntoEntregaCreate,
    PuntoEntregaOut,
    PuntoEntregaUpdate,
    SaldoOut,
)
from app.services import caja, contabilidad, descuentos, entregas, turnos

router = APIRouter(prefix="/contabilidad", tags=["Contabilidad"])


def _punto_out(p: PuntoEntrega) -> dict:
    return {
        "id": p.id, "cliente_id": p.cliente_id, "cliente_nombre": p.cliente.nombre,
        "nombre": p.nombre, "direccion": p.direccion, "latitud": p.latitud, "longitud": p.longitud,
        "ventana_desde": p.ventana_desde, "ventana_hasta": p.ventana_hasta,
        "contacto": p.contacto, "notas": p.notas,
        "repartidor_habitual_id": p.repartidor_habitual_id,
        "dias_entrega": contabilidad.dias_entrega(p), "activo": p.activo,
    }


def _descuento_out(d: DescuentoPunto) -> dict:
    return {
        "id": d.id, "punto_entrega_id": d.punto_entrega_id, "producto_id": d.producto_id,
        "producto_nombre": d.producto.nombre if d.producto else None,
        "porcentaje": d.porcentaje, "motivo": d.motivo, "vigente_desde": d.vigente_desde,
        "vigente_hasta": d.vigente_hasta, "activo": d.activo,
    }


def _movimiento_out(m: MovimientoCuentaCorriente) -> dict:
    return {
        "id": m.id, "tipo": m.tipo, "importe": m.importe, "metodo_pago": m.metodo_pago,
        "referencia": m.referencia, "venta_id": m.venta_id, "turno_id": m.turno_id,
        "corrige_id": m.corrige_id, "usuario": m.usuario.username, "fecha": m.fecha,
        "observacion": m.observacion,
    }


# ---------- Puntos de entrega ----------


@router.get("/puntos-entrega", response_model=list[PuntoEntregaOut])
def listar_puntos(
    _: Gestion,
    db: DB,
    cliente_id: int | None = None,
    buscar: str | None = Query(None, max_length=60),
    incluir_inactivos: bool = False,
):
    puntos = contabilidad.listar_puntos(
        db, cliente_id=cliente_id, buscar=buscar, incluir_inactivos=incluir_inactivos
    )
    return [_punto_out(p) for p in puntos]


@router.post("/puntos-entrega", response_model=PuntoEntregaOut, status_code=status.HTTP_201_CREATED)
def crear_punto(datos: PuntoEntregaCreate, _: Gestion, db: DB):
    return _punto_out(contabilidad.crear_punto(db, datos))


@router.get("/puntos-entrega/{punto_id}", response_model=PuntoEntregaOut)
def ver_punto(punto_id: int, _: Gestion, db: DB):
    return _punto_out(contabilidad.obtener_punto(db, punto_id))


@router.patch("/puntos-entrega/{punto_id}", response_model=PuntoEntregaOut)
def actualizar_punto(punto_id: int, datos: PuntoEntregaUpdate, _: Gestion, db: DB):
    return _punto_out(contabilidad.actualizar_punto(db, punto_id, datos))


@router.get("/puntos-entrega/{punto_id}/plantillas", response_model=list[PlantillaDiaOut])
def ver_plantillas(punto_id: int, _: Gestion, db: DB):
    return contabilidad.obtener_plantillas(db, punto_id)


@router.put("/puntos-entrega/{punto_id}/plantillas", response_model=list[PlantillaDiaOut])
def reemplazar_plantillas(punto_id: int, datos: PlantillasIn, _: Gestion, db: DB):
    return contabilidad.reemplazar_plantillas(db, punto_id, datos)


# ---------- Descuentos ----------


@router.get("/puntos-entrega/{punto_id}/descuentos", response_model=list[DescuentoOut])
def listar_descuentos(punto_id: int, _: Gestion, db: DB):
    return [_descuento_out(d) for d in descuentos.listar_descuentos(db, punto_id)]


@router.post(
    "/puntos-entrega/{punto_id}/descuentos",
    response_model=DescuentoOut,
    status_code=status.HTTP_201_CREATED,
)
def crear_descuento(punto_id: int, datos: DescuentoCreate, _: GestionFuerte, db: DB):
    return _descuento_out(descuentos.crear_descuento(db, punto_id, datos))


@router.patch("/puntos-entrega/{punto_id}/descuentos/{descuento_id}", response_model=DescuentoOut)
def actualizar_descuento(
    punto_id: int, descuento_id: int, datos: DescuentoUpdate, _: GestionFuerte, db: DB
):
    return _descuento_out(descuentos.actualizar_descuento(db, punto_id, descuento_id, datos))


# ---------- Cuenta corriente ----------


@router.get("/saldos", response_model=list[SaldoOut])
def saldos(_: Gestion, db: DB):
    return contabilidad.listar_saldos(db)


@router.get("/clientes/{cliente_id}/cuenta-corriente", response_model=CuentaCorrienteOut)
def cuenta_corriente(
    cliente_id: int,
    _: Gestion,
    db: DB,
    desde: date | None = None,
    hasta: date | None = None,
    limite: int = Query(200, ge=1, le=500),
):
    cliente = contabilidad.obtener_cuenta(db, cliente_id)
    movimientos = contabilidad.listar_movimientos(db, cliente_id, desde=desde, hasta=hasta, limite=limite)
    return {
        "cliente_id": cliente.id, "cliente": cliente.nombre, "cuit": cliente.cuit,
        "saldo": cliente.saldo_cuenta_corriente,
        "movimientos": [_movimiento_out(m) for m in movimientos],
    }


@router.post(
    "/clientes/{cliente_id}/pagos", response_model=MovimientoOut, status_code=status.HTTP_201_CREATED
)
def registrar_pago(cliente_id: int, datos: PagoCuentaCorrienteIn, usuario: GestionORepartidor, db: DB):
    """Cobro de deuda. El repartidor cobra en la calle solo a clientes de su hoja de ruta en
    curso, y el efectivo entra a su turno de reparto."""
    tipo = TipoTurnoEnum.MOSTRADOR
    if usuario.rol == RolEnum.REPARTIDOR:
        entregas.exigir_cliente_en_ruta(db, usuario, cliente_id)
        tipo = TipoTurnoEnum.REPARTO
    turno_id = None
    if datos.metodo_pago == MetodoPagoEnum.EFECTIVO:
        # El efectivo entra al cajón de un turno: se bloquea FOR SHARE (nivel 2 de la
        # jerarquía) para que un cierre simultáneo no lo deje fuera del arqueo.
        turno = caja.exigir_turno_abierto(db, usuario, tipo)
        turno_id = turnos.bloquear_para_cobro(db, turno.id).id
    movimiento = contabilidad.registrar_pago(db, usuario, cliente_id, datos, turno_id)
    return _movimiento_out(movimiento)


@router.post(
    "/clientes/{cliente_id}/notas-credito",
    response_model=MovimientoOut,
    status_code=status.HTTP_201_CREATED,
)
def registrar_nota_credito(cliente_id: int, datos: NotaCreditoIn, usuario: GestionFuerte, db: DB):
    return _movimiento_out(contabilidad.registrar_nota_credito(db, usuario, cliente_id, datos))


@router.post(
    "/clientes/{cliente_id}/ajustes", response_model=MovimientoOut, status_code=status.HTTP_201_CREATED
)
def registrar_ajuste(cliente_id: int, datos: AjusteIn, usuario: GestionFuerte, db: DB):
    return _movimiento_out(contabilidad.registrar_ajuste(db, usuario, cliente_id, datos))
