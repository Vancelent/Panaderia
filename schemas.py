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

class RecetaInsumoCreate(BaseModel):
    producto_id: int
    materia_prima_id: int
    cantidad_necesaria: float

