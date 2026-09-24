from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import EstadoTurnoEnum, MetodoPagoEnum
from app.schemas.common import DineroNoNegativo, DineroOut, ORMModel, Unidades


class TurnoAbrir(BaseModel):
    efectivo_inicial: DineroNoNegativo


class TurnoCerrar(BaseModel):
    monto_declarado: DineroNoNegativo


class TurnoOut(ORMModel):
    """Lo que ve el cajero: sin totales, para no romper el arqueo ciego."""

    id: int
    usuario_id: int
    fecha_apertura: datetime
    efectivo_inicial: DineroOut
    fecha_cierre: datetime | None
    estado: EstadoTurnoEnum


class TurnoCierreOut(BaseModel):
    mensaje: str
    turno_id: int


class ArqueoOut(ORMModel):
    id: int
    turno_id: int
    usuario: str
    fecha_apertura: datetime
    fecha_cierre: datetime | None
    efectivo_inicial: DineroOut
    ventas_efectivo: DineroOut | None
    ventas_otros_medios: DineroOut | None
    monto_sistema: DineroOut
    monto_declarado: DineroOut
    diferencia: DineroOut


class ItemVenta(BaseModel):
    producto_id: int
    cantidad: Unidades


class VentaCreate(BaseModel):
    metodo_pago: MetodoPagoEnum = MetodoPagoEnum.EFECTIVO
    cliente_id: int | None = None
    items: list[ItemVenta] = Field(min_length=1, max_length=200)


class DetalleVentaOut(ORMModel):
    producto_id: int
    nombre: str
    cantidad: int
    precio_unitario: DineroOut
    subtotal: DineroOut


class VentaOut(ORMModel):
    id: int
    turno_id: int
    fecha: datetime
    metodo_pago: MetodoPagoEnum
    monto: DineroOut
    cliente_id: int | None
    detalles: list[DetalleVentaOut]
