from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Cantidad, utcnow
from app.models.inventario import MateriaPrima


class Proveedor(Base):
    __tablename__ = "proveedores"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), index=True)
    cuit: Mapped[str | None] = mapped_column(String(20))
    telefono: Mapped[str | None] = mapped_column(String(40))
    direccion: Mapped[str | None] = mapped_column(String(200))
    notas: Mapped[str | None] = mapped_column(Text)


class CompraMateriaPrima(Base):
    __tablename__ = "compras_materias_primas"

    id: Mapped[int] = mapped_column(primary_key=True)
    proveedor_id: Mapped[int] = mapped_column(ForeignKey("proveedores.id"), index=True)
    materia_prima_id: Mapped[int] = mapped_column(ForeignKey("materias_primas.id"), index=True)
    cantidad_comprada: Mapped[Decimal] = mapped_column(Cantidad)
    precio_total: Mapped[Decimal]
    fecha: Mapped[datetime] = mapped_column(default=utcnow, index=True)

    proveedor: Mapped[Proveedor] = relationship()
    materia_prima: Mapped[MateriaPrima] = relationship()


class GastoVario(Base):
    __tablename__ = "gastos_varios"

    id: Mapped[int] = mapped_column(primary_key=True)
    concepto: Mapped[str] = mapped_column(String(200))
    monto: Mapped[Decimal]
    fecha: Mapped[datetime] = mapped_column(default=utcnow, index=True)
