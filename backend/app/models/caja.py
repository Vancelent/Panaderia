from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow
from app.models.enums import EstadoPagoEnum, EstadoTurnoEnum, MetodoPagoEnum
from app.models.usuario import Usuario


class Turno(Base):
    __tablename__ = "turnos"
    __table_args__ = (
        # Un usuario no puede tener dos turnos abiertos a la vez (lo garantiza la BD).
        Index(
            "uq_turno_abierto_por_usuario",
            "usuario_id",
            unique=True,
            postgresql_where=text("estado = 'ABIERTO'"),
            sqlite_where=text("estado = 'ABIERTO'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    fecha_apertura: Mapped[datetime] = mapped_column(default=utcnow)
    efectivo_inicial: Mapped[Decimal]
    fecha_cierre: Mapped[datetime | None]
    estado: Mapped[EstadoTurnoEnum] = mapped_column(
        Enum(EstadoTurnoEnum), default=EstadoTurnoEnum.ABIERTO
    )

    usuario: Mapped[Usuario] = relationship()
    arqueo: Mapped["Arqueo | None"] = relationship(back_populates="turno")


class Arqueo(Base):
    """Resultado del arqueo ciego. Solo Admin/Encargada pueden leerlo."""

    __tablename__ = "arqueos"

    id: Mapped[int] = mapped_column(primary_key=True)
    turno_id: Mapped[int] = mapped_column(ForeignKey("turnos.id"), unique=True)
    # Efectivo esperado: fondo inicial + ventas en efectivo + cobros de cuenta corriente en efectivo
    monto_sistema: Mapped[Decimal]
    monto_declarado: Mapped[Decimal]
    diferencia: Mapped[Decimal]
    ventas_efectivo: Mapped[Decimal | None]
    ventas_otros_medios: Mapped[Decimal | None]
    cobros_efectivo: Mapped[Decimal | None]
    fecha: Mapped[datetime | None] = mapped_column(default=utcnow)

    turno: Mapped[Turno] = relationship(back_populates="arqueo")


class Venta(Base):
    __tablename__ = "ventas"

    id: Mapped[int] = mapped_column(primary_key=True)
    turno_id: Mapped[int] = mapped_column(ForeignKey("turnos.id"), index=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("clientes.id"), index=True)
    fecha: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    # Medio principal (el de mayor monto). El detalle real de cómo se pagó está en `pagos`.
    metodo_pago: Mapped[MetodoPagoEnum] = mapped_column(
        Enum(MetodoPagoEnum), default=MetodoPagoEnum.EFECTIVO
    )
    monto: Mapped[Decimal]

    detalles: Mapped[list["DetalleVenta"]] = relationship(
        back_populates="venta", cascade="all, delete-orphan"
    )
    pagos: Mapped[list["VentaPago"]] = relationship(
        back_populates="venta", cascade="all, delete-orphan", order_by="VentaPago.id"
    )


class VentaPago(Base):
    """Uno o más pagos por venta (pago mixto). La suma de montos aprobados es el total de la venta."""

    __tablename__ = "ventas_pagos"
    __table_args__ = (CheckConstraint("monto > 0", name="ck_venta_pago_monto_positivo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    venta_id: Mapped[int] = mapped_column(ForeignKey("ventas.id"), index=True)
    metodo_pago: Mapped[MetodoPagoEnum] = mapped_column(Enum(MetodoPagoEnum))
    monto: Mapped[Decimal]
    # Nº de transferencia, cupón o id de QR
    referencia: Mapped[str | None] = mapped_column(String(120))
    estado: Mapped[EstadoPagoEnum] = mapped_column(
        Enum(EstadoPagoEnum), default=EstadoPagoEnum.APROBADO
    )
    # Procesador del posnet/QR, cuando exista una integración
    proveedor: Mapped[str | None] = mapped_column(String(60))
    fecha: Mapped[datetime] = mapped_column(default=utcnow)

    venta: Mapped[Venta] = relationship(back_populates="pagos")


class DetalleVenta(Base):
    __tablename__ = "detalles_venta"

    id: Mapped[int] = mapped_column(primary_key=True)
    venta_id: Mapped[int] = mapped_column(ForeignKey("ventas.id"), index=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"), index=True)
    cantidad: Mapped[int]
    precio_unitario: Mapped[Decimal]
    subtotal: Mapped[Decimal]

    venta: Mapped[Venta] = relationship(back_populates="detalles")
    producto: Mapped["Producto"] = relationship()  # noqa: F821
