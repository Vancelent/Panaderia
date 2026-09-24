from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.common import (
    CantidadInsumo,
    CantidadOut,
    DineroOut,
    DineroPositivo,
    ORMModel,
    Texto,
    TextoLargo,
)


class ProveedorBase(BaseModel):
    nombre: Texto
    cuit: str | None = Field(default=None, max_length=20, pattern=r"^[0-9\-]*$")
    telefono: str | None = Field(default=None, max_length=40)
    direccion: str | None = Field(default=None, max_length=200)
    notas: TextoLargo | None = None


class ProveedorCreate(ProveedorBase):
    pass


class ProveedorOut(ORMModel):
    id: int
    nombre: str
    cuit: str | None
    telefono: str | None
    direccion: str | None
    notas: str | None


class CompraCreate(BaseModel):
    proveedor_id: int
    materia_prima_id: int
    cantidad_comprada: CantidadInsumo
    precio_total: DineroPositivo


class CompraOut(ORMModel):
    id: int
    proveedor_id: int
    proveedor: str
    materia_prima_id: int
    materia_prima: str
    cantidad_comprada: CantidadOut
    precio_total: DineroOut
    fecha: datetime


class GastoCreate(BaseModel):
    concepto: Texto
    monto: DineroPositivo


class GastoOut(ORMModel):
    id: int
    concepto: str
    monto: DineroOut
    fecha: datetime


class VentasPorMedio(BaseModel):
    metodo_pago: str
    total: DineroOut
    cantidad: int


class VentaDiaria(BaseModel):
    fecha: date
    total: DineroOut


class TopProducto(BaseModel):
    producto_id: int
    nombre: str
    unidades: int
    total: DineroOut


class ResumenFinanciero(BaseModel):
    desde: date
    hasta: date
    ventas_totales: DineroOut
    cantidad_ventas: int
    ticket_promedio: DineroOut
    compras_materias_primas: DineroOut
    gastos_operativos: DineroOut
    resultado: DineroOut
    unidades_merma: int
    merma_valorizada: DineroOut
    ventas_por_medio: list[VentasPorMedio]
    ventas_diarias: list[VentaDiaria]
    top_productos: list[TopProducto]
