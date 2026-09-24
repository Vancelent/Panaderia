from datetime import datetime
from decimal import Decimal

from sqlalchemy import Enum, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow
from app.models.enums import EstadoTurnoEnum, MetodoPagoEnum
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
    # Efectivo esperado: fondo inicial + ventas en efectivo
    monto_sistema: Mapped[Decimal]
    monto_declarado: Mapped[Decimal]
    diferencia: Mapped[Decimal]
    ventas_efectivo: Mapped[Decimal | None]
    ventas_otros_medios: Mapped[Decimal | None]
    fecha: Mapped[datetime | None] = mapped_column(default=utcnow)

    turno: Mapped[Turno] = relationship(back_populates="arqueo")


class Venta(Base):
    __tablename__ = "ventas"

    id: Mapped[int] = mapped_column(primary_key=True)
    turno_id: Mapped[int] = mapped_column(ForeignKey("turnos.id"), index=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("clientes.id"), index=True)
    fecha: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    metodo_pago: Mapped[MetodoPagoEnum] = mapped_column(
        Enum(MetodoPagoEnum), default=MetodoPagoEnum.EFECTIVO
    )
    monto: Mapped[Decimal]

    detalles: Mapped[list["DetalleVenta"]] = relationship(
        back_populates="venta", cascade="all, delete-orphan"
    )


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
