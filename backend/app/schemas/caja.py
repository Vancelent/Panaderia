from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import EstadoPagoEnum, EstadoTurnoEnum, MetodoPagoEnum
from app.schemas.common import DineroNoNegativo, DineroOut, DineroPositivo, ORMModel, Texto, Unidades


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
    cobros_efectivo: DineroOut | None
    monto_sistema: DineroOut
    monto_declarado: DineroOut
    diferencia: DineroOut


class ItemVenta(BaseModel):
    producto_id: int
    cantidad: Unidades


class PagoIn(BaseModel):
    """Un medio de pago de una venta. Los montos son netos: el vuelto no se guarda."""

    metodo_pago: MetodoPagoEnum
    monto: DineroPositivo
    referencia: Texto | None = None         # nº de transferencia, cupón o id de QR


class VentaCreate(BaseModel):
    # Un solo medio por el total (como hasta ahora). Se ignora si llega `pagos`.
    metodo_pago: MetodoPagoEnum = MetodoPagoEnum.EFECTIVO
    # Pago mixto: la suma debe ser igual al total que calcula el servidor (`pagos_no_cuadran`)
    pagos: list[PagoIn] | None = Field(default=None, min_length=1, max_length=5)
    cliente_id: int | None = None
    items: list[ItemVenta] = Field(min_length=1, max_length=200)


class MediosPagoOut(BaseModel):
    habilitados: list[MetodoPagoEnum]       # medios que ofrece la caja
    cuenta_corriente: bool = True           # se ofrece cuando la venta tiene cliente


class DetalleVentaOut(ORMModel):
    producto_id: int
    nombre: str
    cantidad: int
    precio_unitario: DineroOut
    subtotal: DineroOut


class PagoOut(ORMModel):
    metodo_pago: MetodoPagoEnum
    monto: DineroOut
    referencia: str | None
    estado: EstadoPagoEnum


class VentaOut(ORMModel):
    id: int
    turno_id: int
    fecha: datetime
    metodo_pago: MetodoPagoEnum             # medio principal (el de mayor monto)
    monto: DineroOut
    cliente_id: int | None
    detalles: list[DetalleVentaOut]
    pagos: list[PagoOut]
