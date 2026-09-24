from datetime import datetime
from decimal import Decimal

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow
from app.models.enums import EstadoPedidoEnum
from app.models.inventario import Producto


class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), index=True)
    telefono: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(120))
    direccion: Mapped[str | None] = mapped_column(String(200))
    notas: Mapped[str | None] = mapped_column(Text)
    activo: Mapped[bool] = mapped_column(default=True, server_default="true")
    creado_en: Mapped[datetime] = mapped_column(default=utcnow)


class Pedido(Base):
    """Encargo / comanda. Al entregarse se cobra y genera una Venta."""

    __tablename__ = "pedidos"

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("clientes.id"), index=True)
    # Nombre de contacto para pedidos de mostrador sin cliente registrado
    contacto: Mapped[str | None] = mapped_column(String(120))
    estado: Mapped[EstadoPedidoEnum] = mapped_column(
        Enum(EstadoPedidoEnum), default=EstadoPedidoEnum.PENDIENTE, index=True
    )
    fecha_entrega: Mapped[datetime] = mapped_column(index=True)
    notas: Mapped[str | None] = mapped_column(Text)
    total: Mapped[Decimal]
    creado_por_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = mapped_column(default=utcnow)
    actualizado_en: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    venta_id: Mapped[int | None] = mapped_column(ForeignKey("ventas.id"))

    cliente: Mapped[Cliente | None] = relationship()
    detalles: Mapped[list["DetallePedido"]] = relationship(
        back_populates="pedido", cascade="all, delete-orphan", order_by="DetallePedido.id"
    )


class DetallePedido(Base):
    __tablename__ = "detalles_pedido"

    id: Mapped[int] = mapped_column(primary_key=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedidos.id"), index=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"))
    cantidad: Mapped[int]
    precio_unitario: Mapped[Decimal]
    subtotal: Mapped[Decimal]

    pedido: Mapped[Pedido] = relationship(back_populates="detalles")
    producto: Mapped[Producto] = relationship()
