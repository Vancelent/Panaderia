from datetime import date, datetime, time
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.models.enums import MetodoPagoEnum, TipoMovimientoCtaCteEnum
from app.schemas.common import (
    DineroOut,
    DineroPositivo,
    ORMModel,
    Texto,
    TextoLargo,
    TextoOpcional,
    Unidades,
)

Latitud = Annotated[Decimal, Field(ge=-90, le=90, max_digits=9, decimal_places=6)]
Longitud = Annotated[Decimal, Field(ge=-180, le=180, max_digits=9, decimal_places=6)]
Porcentaje = Annotated[Decimal, Field(gt=0, le=100, max_digits=5, decimal_places=2)]
DiaSemana = Annotated[int, Field(ge=0, le=6)]  # 0 = lunes … 6 = domingo
ImporteAjuste = Annotated[Decimal, Field(max_digits=12, decimal_places=2)]

# ---------- Puntos de entrega ----------


class _PuntoCampos(BaseModel):
    nombre: Texto | None = None
    direccion: TextoOpcional = None
    latitud: Latitud | None = None
    longitud: Longitud | None = None
    ventana_desde: time | None = None
    ventana_hasta: time | None = None
    contacto: Texto | None = None
    notas: TextoLargo | None = None
    repartidor_habitual_id: int | None = None

    @model_validator(mode="after")
    def _coherencia(self):
        if (self.latitud is None) != (self.longitud is None):
            raise ValueError("Indicá latitud y longitud juntas, o ninguna.")
        if (self.ventana_desde is None) != (self.ventana_hasta is None):
            raise ValueError("Indicá el horario de recepción completo (desde y hasta), o ninguno.")
        if self.ventana_desde and self.ventana_hasta and self.ventana_desde >= self.ventana_hasta:
            raise ValueError("El horario 'desde' debe ser anterior a 'hasta'.")
        return self


class PuntoEntregaCreate(_PuntoCampos):
    cliente_id: int
    nombre: Texto  # obligatorio al crear


class PuntoEntregaUpdate(_PuntoCampos):
    # Mover un punto a otro cliente cambiaría de cuenta corriente: no se permite.
    activo: bool | None = None


class PuntoEntregaOut(ORMModel):
    id: int
    cliente_id: int
    cliente_nombre: str
    nombre: str
    direccion: str | None
    latitud: DineroOut | None
    longitud: DineroOut | None
    ventana_desde: time | None
    ventana_hasta: time | None
    contacto: str | None
    notas: str | None
    repartidor_habitual_id: int | None
    dias_entrega: list[int]                 # días con pedido fijo (0 = lunes)
    activo: bool


# ---------- Plantillas (pedido fijo por día) ----------


class PlantillaItemIn(BaseModel):
    producto_id: int
    cantidad: Unidades


class PlantillaDiaIn(BaseModel):
    dia_semana: DiaSemana
    items: list[PlantillaItemIn] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def _sin_repetidos(self):
        ids = [i.producto_id for i in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Hay productos repetidos en el mismo día.")
        return self


class PlantillasIn(BaseModel):
    """Reemplaza todas las plantillas del punto. Un día sin items deja de ser día de entrega."""

    dias: list[PlantillaDiaIn] = Field(max_length=7)

    @model_validator(mode="after")
    def _dias_unicos(self):
        dias = [d.dia_semana for d in self.dias]
        if len(dias) != len(set(dias)):
            raise ValueError("Hay días de la semana repetidos.")
        return self


class PlantillaItemOut(BaseModel):
    producto_id: int
    nombre: str
    cantidad: int


class PlantillaDiaOut(BaseModel):
    dia_semana: int
    items: list[PlantillaItemOut]


# ---------- Descuentos ----------


class DescuentoCreate(BaseModel):
    producto_id: int | None = None          # None = descuento general del punto
    porcentaje: Porcentaje
    motivo: Texto
    vigente_desde: date | None = None
    vigente_hasta: date | None = None


class DescuentoUpdate(BaseModel):
    porcentaje: Porcentaje | None = None
    motivo: Texto | None = None
    vigente_desde: date | None = None
    vigente_hasta: date | None = None
    activo: bool | None = None


class DescuentoOut(ORMModel):
    id: int
    punto_entrega_id: int
    producto_id: int | None
    producto_nombre: str | None
    porcentaje: DineroOut
    motivo: str
    vigente_desde: date | None
    vigente_hasta: date | None
    activo: bool


# ---------- Cuenta corriente ----------


class _OperacionIdempotente(BaseModel):
    # Generado por la app: reenviar la misma operación no la duplica
    operacion_id: UUID | None = None


class PagoCuentaCorrienteIn(_OperacionIdempotente):
    monto: DineroPositivo
    metodo_pago: MetodoPagoEnum = MetodoPagoEnum.EFECTIVO
    referencia: Texto | None = None
    observacion: TextoOpcional = None

    @model_validator(mode="after")
    def _no_cuenta_corriente(self):
        if self.metodo_pago == MetodoPagoEnum.CUENTA_CORRIENTE:
            raise ValueError("Un pago no puede hacerse con cuenta corriente.")
        return self


class NotaCreditoIn(_OperacionIdempotente):
    monto: DineroPositivo
    observacion: Texto                      # obligatoria: queda auditada
    corrige_id: int | None = None


class AjusteIn(_OperacionIdempotente):
    importe: ImporteAjuste                  # + aumenta la deuda, − la reduce
    observacion: Texto
    corrige_id: int | None = None

    @model_validator(mode="after")
    def _no_cero(self):
        if self.importe == 0:
            raise ValueError("El importe del ajuste no puede ser cero.")
        return self


class MovimientoOut(ORMModel):
    id: int
    tipo: TipoMovimientoCtaCteEnum
    importe: DineroOut
    metodo_pago: MetodoPagoEnum | None
    referencia: str | None
    venta_id: int | None
    turno_id: int | None
    corrige_id: int | None
    usuario: str
    fecha: datetime
    observacion: str | None


class CuentaCorrienteOut(BaseModel):
    cliente_id: int
    cliente: str
    cuit: str | None
    saldo: DineroOut                        # + = el cliente debe
    movimientos: list[MovimientoOut]


class SaldoOut(BaseModel):
    cliente_id: int
    cliente: str
    saldo: DineroOut
    ultimo_movimiento: datetime | None
