from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import (
    CantidadInsumo,
    CantidadInsumoNoNeg,
    CantidadOut,
    DineroOut,
    DineroPositivo,
    ORMModel,
    Texto,
    Unidades,
)

# ---------- Productos ----------


class ProductoBase(BaseModel):
    nombre: Texto
    categoria: Texto | None = None
    precio_venta: DineroPositivo
    stock_minimo: int = Field(default=0, ge=0, le=100_000)


class ProductoCreate(ProductoBase):
    stock_mostrador: int = Field(default=0, ge=0, le=100_000)


class ProductoUpdate(BaseModel):
    nombre: Texto | None = None
    categoria: Texto | None = None
    precio_venta: DineroPositivo | None = None
    stock_minimo: int | None = Field(default=None, ge=0, le=100_000)
    activo: bool | None = None


class ProductoOut(ORMModel):
    id: int
    nombre: str
    categoria: str | None
    precio_venta: DineroOut
    stock_mostrador: int
    stock_minimo: int
    activo: bool


class AjusteStockProducto(BaseModel):
    """Corrección manual de stock (conteo físico). Solo Admin/Encargada."""

    stock_mostrador: int = Field(ge=0, le=100_000)


# ---------- Materias primas y recetas ----------


class MateriaPrimaCreate(BaseModel):
    nombre: Texto
    unidad_medida: str = Field(min_length=1, max_length=20)
    stock_actual: CantidadInsumoNoNeg = 0
    stock_minimo: CantidadInsumoNoNeg = 0


class MateriaPrimaUpdate(BaseModel):
    nombre: Texto | None = None
    unidad_medida: str | None = Field(default=None, min_length=1, max_length=20)
    stock_minimo: CantidadInsumoNoNeg | None = None
    stock_actual: CantidadInsumoNoNeg | None = None


class MateriaPrimaOut(ORMModel):
    id: int
    nombre: str
    unidad_medida: str
    stock_actual: CantidadOut
    stock_minimo: CantidadOut
    costo_unitario_actual: CantidadOut


class RecetaItemIn(BaseModel):
    materia_prima_id: int
    cantidad_necesaria: CantidadInsumo


class RecetaIn(BaseModel):
    """Reemplaza la receta completa de un producto."""

    insumos: list[RecetaItemIn] = Field(max_length=50)


class RecetaItemOut(ORMModel):
    materia_prima_id: int
    materia_prima: str
    unidad_medida: str
    cantidad_necesaria: CantidadOut
    costo: DineroOut


class RecetaOut(BaseModel):
    producto_id: int
    insumos: list[RecetaItemOut]
    costo_unitario: DineroOut


# ---------- Producción y mermas ----------


class LoteItem(BaseModel):
    producto_id: int
    cantidad: Unidades


class ProduccionIn(BaseModel):
    lotes: list[LoteItem] = Field(min_length=1, max_length=100)


class LoteOut(ORMModel):
    id: int
    producto_id: int
    cantidad_producida: int
    fecha_hora: datetime


class ConsumoInsumo(BaseModel):
    materia_prima_id: int
    nombre: str
    cantidad: CantidadOut
    unidad_medida: str


class ProduccionOut(BaseModel):
    lotes: list[LoteOut]
    unidades_totales: int
    insumos_consumidos: list[ConsumoInsumo]


class MermaCreate(BaseModel):
    producto_id: int
    cantidad_perdida: Unidades
    motivo: Texto


class MermaOut(ORMModel):
    id: int
    producto_id: int
    cantidad_perdida: int
    motivo: str
    fecha_hora: datetime
