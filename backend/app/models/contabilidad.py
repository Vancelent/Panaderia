import uuid
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Enum,
    ForeignKey,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow
from app.models.comercial import Cliente
from app.models.enums import MetodoPagoEnum, TipoMovimientoCtaCteEnum
from app.models.inventario import Producto
from app.models.usuario import Usuario

Coordenada = Numeric(9, 6)  # ~11 cm de precisión; no es dinero, pero tampoco se guarda como float
Porcentaje = Numeric(5, 2)


class PuntoEntrega(Base):
    """Local de un cliente mayorista o sucursal al que se reparte.

    Un cliente puede tener varios puntos y todos comparten una sola cuenta corriente.
    """

    __tablename__ = "puntos_entrega"

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(120), index=True)
    direccion: Mapped[str | None] = mapped_column(String(200))
    latitud: Mapped[Decimal | None] = mapped_column(Coordenada)
    longitud: Mapped[Decimal | None] = mapped_column(Coordenada)
    ventana_desde: Mapped[time | None]
    ventana_hasta: Mapped[time | None]
    contacto: Mapped[str | None] = mapped_column(String(120))
    notas: Mapped[str | None] = mapped_column(Text)
    repartidor_habitual_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    activo: Mapped[bool] = mapped_column(default=True, server_default="true")
    creado_en: Mapped[datetime] = mapped_column(default=utcnow)

    cliente: Mapped[Cliente] = relationship()
    descuentos: Mapped[list["DescuentoPunto"]] = relationship(
        back_populates="punto", cascade="all, delete-orphan", order_by="DescuentoPunto.id"
    )
    plantillas: Mapped[list["PlantillaEntrega"]] = relationship(
        back_populates="punto",
        cascade="all, delete-orphan",
        order_by="(PlantillaEntrega.dia_semana, PlantillaEntrega.id)",
    )


class DescuentoPunto(Base):
    """Descuento porcentual de un punto de entrega: general (producto NULL) o por producto."""

    __tablename__ = "descuentos_punto"
    __table_args__ = (
        CheckConstraint("porcentaje > 0 AND porcentaje <= 100", name="ck_descuento_porcentaje"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    punto_entrega_id: Mapped[int] = mapped_column(ForeignKey("puntos_entrega.id"), index=True)
    producto_id: Mapped[int | None] = mapped_column(ForeignKey("productos.id"))
    porcentaje: Mapped[Decimal] = mapped_column(Porcentaje)
    motivo: Mapped[str] = mapped_column(String(120))
    vigente_desde: Mapped[date | None]
    vigente_hasta: Mapped[date | None]
    activo: Mapped[bool] = mapped_column(default=True, server_default="true")

    punto: Mapped[PuntoEntrega] = relationship(back_populates="descuentos")
    producto: Mapped[Producto | None] = relationship()


class PlantillaEntrega(Base):
    """Pedido fijo de un punto para un día de la semana (0 = lunes … 6 = domingo).

    Los días con alguna fila son los "días de entrega" del punto.
    """

    __tablename__ = "plantillas_entrega"
    __table_args__ = (
        UniqueConstraint("punto_entrega_id", "dia_semana", "producto_id"),
        CheckConstraint("dia_semana >= 0 AND dia_semana <= 6", name="ck_plantilla_dia"),
        CheckConstraint("cantidad > 0", name="ck_plantilla_cantidad"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    punto_entrega_id: Mapped[int] = mapped_column(ForeignKey("puntos_entrega.id"), index=True)
    dia_semana: Mapped[int] = mapped_column(SmallInteger)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"))
    cantidad: Mapped[int]

    punto: Mapped[PuntoEntrega] = relationship(back_populates="plantillas")
    producto: Mapped[Producto] = relationship()


class MovimientoCuentaCorriente(Base):
    """Libro inmutable de la cuenta corriente de un cliente.

    `importe` lleva signo: positivo aumenta la deuda (CARGO), negativo la reduce
    (PAGO, NOTA_CREDITO); un AJUSTE puede ir en cualquier sentido. Un error se corrige
    con un AJUSTE que referencia al movimiento original, nunca con UPDATE ni DELETE.
    """

    __tablename__ = "movimientos_cuenta_corriente"
    __table_args__ = (CheckConstraint("importe <> 0", name="ck_movimiento_importe_no_cero"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), index=True)
    punto_entrega_id: Mapped[int | None] = mapped_column(ForeignKey("puntos_entrega.id"))
    tipo: Mapped[TipoMovimientoCtaCteEnum] = mapped_column(Enum(TipoMovimientoCtaCteEnum))
    importe: Mapped[Decimal]
    # Solo en PAGO: cómo pagó el cliente
    metodo_pago: Mapped[MetodoPagoEnum | None] = mapped_column(Enum(MetodoPagoEnum))
    referencia: Mapped[str | None] = mapped_column(String(120))
    venta_id: Mapped[int | None] = mapped_column(ForeignKey("ventas.id"))
    # Turno en el que entró el efectivo, para que cuente en su arqueo
    turno_id: Mapped[int | None] = mapped_column(ForeignKey("turnos.id"), index=True)
    # Movimiento original al que corrige o compensa este
    corrige_id: Mapped[int | None] = mapped_column(ForeignKey("movimientos_cuenta_corriente.id"))
    # Idempotencia de reintentos (app móvil): una operación se aplica una sola vez
    operacion_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, unique=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    fecha: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    observacion: Mapped[str | None] = mapped_column(String(200))

    cliente: Mapped[Cliente] = relationship()
    usuario: Mapped[Usuario] = relationship()
