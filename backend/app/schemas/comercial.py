from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, EmailStr, Field, StringConstraints, model_validator

from app.models.enums import EstadoPedidoEnum, MetodoPagoEnum
from app.schemas.common import DineroOut, ORMModel, Texto, TextoLargo, TextoOpcional, Unidades

Cuit = Annotated[str, StringConstraints(strip_whitespace=True, max_length=20, pattern=r"^[0-9\-]*$")]
Telefono = Annotated[str, StringConstraints(strip_whitespace=True, max_length=40,
                                            pattern=r"^[0-9+()\-\s]*$")]

# ---------- Clientes ----------


class ClienteBase(BaseModel):
    nombre: Texto
    telefono: Telefono | None = None
    email: EmailStr | None = None
    direccion: TextoOpcional = None
    cuit: Cuit | None = None
    notas: TextoLargo | None = None


class ClienteCreate(ClienteBase):
    pass


class ClienteUpdate(BaseModel):
    nombre: Texto | None = None
    telefono: Telefono | None = None
    email: EmailStr | None = None
    direccion: TextoOpcional = None
    cuit: Cuit | None = None
    notas: TextoLargo | None = None
    activo: bool | None = None


class ClienteOut(ORMModel):
    id: int
    nombre: str
    telefono: str | None
    email: str | None
    direccion: str | None
    cuit: str | None
    saldo_cuenta_corriente: DineroOut
    notas: str | None
    activo: bool
    creado_en: datetime


# ---------- Pedidos ----------


class ItemPedido(BaseModel):
    producto_id: int
    cantidad: Unidades


class PedidoCreate(BaseModel):
    cliente_id: int | None = None
    contacto: Texto | None = None
    fecha_entrega: datetime
    notas: TextoLargo | None = None
    items: list[ItemPedido] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def _cliente_o_contacto(self):
        if self.cliente_id is None and not self.contacto:
            raise ValueError("Indicá un cliente registrado o un nombre de contacto.")
        return self


class PedidoUpdate(BaseModel):
    """Editar un pedido que todavía no se empezó a preparar."""

    fecha_entrega: datetime | None = None
    notas: TextoLargo | None = None
    contacto: Texto | None = None
    items: list[ItemPedido] | None = Field(default=None, min_length=1, max_length=100)


class CambioEstadoPedido(BaseModel):
    estado: EstadoPedidoEnum


class EntregaPedido(BaseModel):
    metodo_pago: MetodoPagoEnum = MetodoPagoEnum.EFECTIVO


class DetallePedidoOut(ORMModel):
    producto_id: int
    nombre: str
    cantidad: int
    precio_unitario: DineroOut
    subtotal: DineroOut


class PedidoOut(ORMModel):
    id: int
    cliente_id: int | None
    cliente_nombre: str | None
    contacto: str | None
    estado: EstadoPedidoEnum
    fecha_entrega: datetime
    notas: str | None
    total: DineroOut
    creado_en: datetime
    venta_id: int | None
    detalles: list[DetallePedidoOut]


class PendienteProduccion(BaseModel):
    producto_id: int
    nombre: str
    cantidad_pedida: int
    stock_mostrador: int
    faltante: int
