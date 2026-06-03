from pydantic import BaseModel
from models import RolEnum

class UsuarioCreate(BaseModel):
    username: str
    rol: RolEnum
    password: str

class TurnoCreate(BaseModel):
    efectivo_inicial: float

class ProductoCreate(BaseModel):
    nombre: str
    precio_venta: float
    stock_mostrador: int

class ProductoOut(BaseModel):
    id: int
    nombre: str
    precio_venta: float
    stock_mostrador: int

    class Config:
        from_attributes = True

class DetalleVentaCreate(BaseModel):
    producto_id: int
    cantidad: int

class VentaCreate(BaseModel):
    turno_id: int
    detalles: list[DetalleVentaCreate]
    metodo_pago: str = "Efectivo"

class TurnoCierre(BaseModel):
    monto_declarado: float

class ArqueoOut(BaseModel):
    id: int
    turno_id: int
    monto_sistema: float
    monto_declarado: float
    diferencia: float

    class Config:
        from_attributes = True

class LoteProduccionCreate(BaseModel):
    producto_id: int
    cantidad_producida: int

class MermaCreate(BaseModel):
    producto_id: int
    cantidad_perdida: int
    motivo: str

class MateriaPrimaCreate(BaseModel):
    nombre: str
    stock_actual_kg: float
    unidad_medida: str

class MateriaPrimaUpdate(BaseModel):
    nombre: str | None = None
    stock_actual_kg: float | None = None
    unidad_medida: str | None = None

class RecetaItem(BaseModel):
    materia_prima_id: int
    cantidad_necesaria: float

class ProductoUpdate(BaseModel):
    nombre: str | None = None
    precio_venta: float | None = None
    recetas: list[RecetaItem] | None = None

class RecetaInsumoCreate(BaseModel):
    producto_id: int
    materia_prima_id: int
    cantidad_necesaria: float

class ProduccionBulkItem(BaseModel):
    producto_id: int
    cantidad: int

class ProduccionBulkRequest(BaseModel):
    productos: list[ProduccionBulkItem]

class ProveedorCreate(BaseModel):
    nombre: str
    cuit: str | None = None
    telefono: str | None = None
    direccion: str | None = None
    notas: str | None = None

class CompraMateriaPrimaCreate(BaseModel):
    proveedor_id: int
    materia_prima_id: int
    cantidad_comprada: float
    precio_total: float
    metodo_pago: str = "Efectivo"

class GastoVarioCreate(BaseModel):
    concepto: str
    monto: float
    metodo_pago: str = "Efectivo"

class AuditoriaInventarioCreate(BaseModel):
    materia_prima_id: int
    stock_real: float

class ProductoUpdatePrecio(BaseModel):
    nuevo_precio: float
