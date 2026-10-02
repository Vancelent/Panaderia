"""Contratos del reparto (docs/rfc-001 §3.7). Los importes son Decimal; las coordenadas y
distancias no son dinero pero tampoco se guardan como float."""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, BaseModel, BeforeValidator, Field, model_validator

from app.models.enums import (
    DestinoDevolucionEnum,
    EstadoEntregaEnum,
    EstadoHojaRutaEnum,
    MetodoPagoEnum,
    TipoEventoRecorridoEnum,
)
from app.schemas.caja import PagoIn
from app.schemas.common import DineroNoNegativo, DineroOut, ORMModel, Texto, Unidades

SEIS_DECIMALES = Decimal("0.000001")
UN_DECIMAL = Decimal("0.1")


def _redondear(cuantizador: Decimal):
    """Un GPS entrega 15 decimales: se redondean al guardar en lugar de rechazar el dato."""

    def _f(v):
        if isinstance(v, (int, float, str, Decimal)) and not isinstance(v, bool):
            try:
                return Decimal(str(v)).quantize(cuantizador)
            except Exception:  # noqa: BLE001  (lo rechaza la validación de tipo)
                return v
        return v

    return _f


Latitud = Annotated[Decimal, BeforeValidator(_redondear(SEIS_DECIMALES)), Field(ge=-90, le=90)]
Longitud = Annotated[Decimal, BeforeValidator(_redondear(SEIS_DECIMALES)), Field(ge=-180, le=180)]
Precision = Annotated[Decimal, BeforeValidator(_redondear(UN_DECIMAL)), Field(ge=0, le=100000)]

# Un reloj de dispositivo que se pasa de este rango es un error, no un dato
MAX_ANTIGUEDAD = timedelta(days=30)
MAX_ADELANTO = timedelta(days=1)


def _a_utc_acotado(v: datetime | None) -> datetime | None:
    if v is None:
        return None
    if v.tzinfo is None:
        v = v.replace(tzinfo=UTC)
    v = v.astimezone(UTC)
    ahora = datetime.now(UTC)
    if v < ahora - MAX_ANTIGUEDAD or v > ahora + MAX_ADELANTO:
        raise ValueError("La fecha y hora del dispositivo está fuera de rango (revisá el reloj).")
    return v


Instante = Annotated[datetime, AfterValidator(_a_utc_acotado)]
InstanteOpc = Annotated[datetime | None, AfterValidator(_a_utc_acotado)]


class PosicionIn(BaseModel):
    latitud: Latitud
    longitud: Longitud
    precision_m: Precision | None = None
    registrado_en: Instante              # reloj del dispositivo


# ---------- Hoja de ruta (armado y carga) ----------


class ItemHojaIn(BaseModel):
    producto_id: int
    cantidad: Unidades


class ParadaIn(BaseModel):
    punto_entrega_id: int
    items: list[ItemHojaIn] = Field(min_length=1, max_length=100)


class HojaRutaCreate(BaseModel):
    fecha: date
    repartidor_id: int
    paradas: list[ParadaIn] = Field(min_length=1, max_length=80)


class HojaRutaUpdate(BaseModel):
    """Solo en borrador. Si llegan `paradas`, reemplazan a todas las anteriores."""

    fecha: date | None = None
    repartidor_id: int | None = None
    paradas: list[ParadaIn] | None = Field(default=None, min_length=1, max_length=80)


class ItemCargaIn(BaseModel):
    producto_id: int
    cantidad: int = Field(ge=0, le=100_000)


class CargaIn(BaseModel):
    """Lo efectivamente cargado. Lo que falte de lo reservado se libera para la caja."""

    items: list[ItemCargaIn] = Field(max_length=200)
    fondo_inicial: DineroNoNegativo = Decimal("0")   # cambio con el que sale el repartidor


# ---------- Operaciones de la app (idempotentes) ----------


class OperacionMovil(BaseModel):
    operacion_id: UUID                   # generado en el dispositivo (UUID v4)
    posicion: PosicionIn | None = None   # None si el GPS no estaba disponible
    registrado_en: InstanteOpc = None    # reloj del dispositivo, solo informativo


class InicioRutaIn(OperacionMovil):
    # El dispositivo informa si la persona concedió el permiso de ubicación. Sin él no se sale
    # a la ruta: el recorrido real es obligatorio (D18).
    ubicacion_concedida: bool


class ItemEntregaIn(BaseModel):
    producto_id: int
    cantidad_entregada: int = Field(ge=0, le=100_000)


class ConfirmacionEntregaIn(OperacionMovil):
    items: list[ItemEntregaIn] = Field(min_length=1, max_length=100)
    # Lo que se cobró en el momento. Lo que quede sin pagar va a la cuenta corriente.
    pagos: list[PagoIn] = Field(default_factory=list, max_length=5)
    recibio_nombre: Texto | None = None

    @model_validator(mode="after")
    def _validar(self):
        ids = [i.producto_id for i in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Hay productos repetidos en la entrega.")
        if any(p.metodo_pago == MetodoPagoEnum.CUENTA_CORRIENTE for p in self.pagos):
            raise ValueError("Lo que no se cobra queda solo a cuenta corriente: no lo informes como pago.")
        return self


class NoEntregadaIn(OperacionMovil):
    motivo: Texto


# ---------- Recorrido GPS ----------


class EventoRecorridoIn(BaseModel):
    tipo: TipoEventoRecorridoEnum
    desde: Instante
    hasta: InstanteOpc = None

    @model_validator(mode="after")
    def _orden(self):
        if self.hasta is not None and self.hasta < self.desde:
            raise ValueError("El corte no puede terminar antes de empezar.")
        return self


class RecorridoLoteIn(BaseModel):
    lote_id: UUID                        # reenviar el mismo lote no duplica puntos
    puntos: list[PosicionIn] = Field(default_factory=list, max_length=500)
    eventos: list[EventoRecorridoIn] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def _algo(self):
        if not self.puntos and not self.eventos:
            raise ValueError("El lote no trae puntos ni eventos.")
        return self


class LoteOut(BaseModel):
    recibidos: int
    nuevos: int                          # los repetidos no cuentan
    eventos_nuevos: int


# ---------- Rendición ----------


class DevolucionIn(BaseModel):
    producto_id: int
    cantidad: Unidades
    destino: DestinoDevolucionEnum       # REINGRESO (vuelve a vender) o MERMA (se pierde)


class RendicionIn(BaseModel):
    devoluciones: list[DevolucionIn] = Field(default_factory=list, max_length=200)
    efectivo_declarado: DineroNoNegativo  # arqueo ciego: la respuesta no incluye la diferencia


# ---------- Salidas ----------


class ItemEntregaOut(BaseModel):
    producto_id: int
    nombre: str
    cantidad_planificada: int
    cantidad_entregada: int
    precio_lista: DineroOut
    descuento_pct: DineroOut | None
    precio_unitario: DineroOut
    subtotal: DineroOut                  # planificado, o entregado si la entrega ya se hizo


class EntregaOut(ORMModel):
    id: int
    hoja_id: int
    punto_entrega_id: int
    punto_nombre: str
    cliente_id: int
    cliente_nombre: str
    direccion: str | None
    latitud: DineroOut | None            # ubicación del punto
    longitud: DineroOut | None
    ventana_desde: time | None
    ventana_hasta: time | None
    contacto: str | None
    notas: str | None
    orden_sugerido: int
    orden_real: int | None
    estado: EstadoEntregaEnum
    numero_remito: int | None
    motivo_no_entrega: str | None
    total: DineroOut
    cobrado: DineroOut
    saldo_cliente: DineroOut             # cuenta corriente del cliente tras la operación
    items: list[ItemEntregaOut]


class CargaItemOut(BaseModel):
    producto_id: int
    nombre: str
    reservada: int
    cargada: int
    entregada: int
    devuelta: int


class HojaRutaOut(BaseModel):
    id: int
    fecha: date
    estado: EstadoHojaRutaEnum
    repartidor_id: int
    repartidor: str
    turno_id: int | None
    total_planificado: DineroOut
    distancia_sugerida_km: DineroOut | None
    distancia_real_km: DineroOut | None
    confirmada_en: datetime | None
    cargada_en: datetime | None
    iniciada_en: datetime | None
    rendida_en: datetime | None
    entregas: list[EntregaOut]
    carga: list[CargaItemOut]


class HojaRutaResumenOut(BaseModel):
    id: int
    fecha: date
    estado: EstadoHojaRutaEnum
    repartidor_id: int
    repartidor: str
    paradas: int
    entregadas: int                      # entregas ya resueltas (entregada, parcial o no entregada)
    pendientes: int
    total_planificado: DineroOut
    distancia_sugerida_km: DineroOut | None


class OmitidoOut(BaseModel):
    punto: str
    motivo: str


class GeneracionOut(BaseModel):
    hojas: list[HojaRutaResumenOut]
    omitidos: list[OmitidoOut]


class RepartidorOut(ORMModel):
    id: int
    username: str
    nombre: str | None


class ResumenEntregasOut(BaseModel):
    fecha: date
    hojas: int
    paradas: int
    completadas: int                     # entregadas por completo
    parciales: int
    no_entregadas: int
    pendientes: int                      # pendientes o en el local
    facturacion_reparto: DineroOut       # ventas del reparto de ese día
    cobrado: DineroOut                   # lo cobrado en el momento (sin cuenta corriente)
    a_cuenta_corriente: DineroOut


# ---------- Mapa de recorrido ----------


class PuntoSugeridoOut(BaseModel):
    entrega_id: int
    orden_sugerido: int
    nombre: str
    latitud: DineroOut
    longitud: DineroOut


class PuntoTrazaOut(BaseModel):
    latitud: DineroOut
    longitud: DineroOut
    registrado_en: datetime


class EntregaMapaOut(BaseModel):
    entrega_id: int
    punto_nombre: str
    estado: EstadoEntregaEnum
    orden_sugerido: int
    orden_real: int | None
    latitud: DineroOut | None            # donde se confirmó
    longitud: DineroOut | None
    punto_latitud: DineroOut | None      # donde está el punto
    punto_longitud: DineroOut | None
    hora: datetime | None
    distancia_al_punto_m: int | None
    lejos: bool                          # alerta, no bloqueo


class EventoRecorridoOut(BaseModel):
    tipo: TipoEventoRecorridoEnum
    desde: datetime
    hasta: datetime | None


class IndicadoresOut(BaseModel):
    distancia_sugerida_km: DineroOut | None
    distancia_real_km: DineroOut | None
    duracion_min: int | None
    entregas_fuera_de_orden: int
    entregas_lejos: int
    tramos_sin_traza: int


class RecorridoOut(BaseModel):
    hoja_id: int
    estado: EstadoHojaRutaEnum
    origen: dict | None
    sugerida: list[PuntoSugeridoOut]
    traza: list[PuntoTrazaOut]           # simplificada (Douglas-Peucker)
    puntos_totales: int
    entregas: list[EntregaMapaOut]
    eventos: list[EventoRecorridoOut]
    indicadores: IndicadoresOut
