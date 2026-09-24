from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Cantidad, CostoUnitario, utcnow


class Producto(Base):
    __tablename__ = "productos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), index=True)
    categoria: Mapped[str | None] = mapped_column(String(60))
    precio_venta: Mapped[Decimal]
    stock_mostrador: Mapped[int] = mapped_column(default=0)
    stock_minimo: Mapped[int] = mapped_column(default=0, server_default="0")
    activo: Mapped[bool] = mapped_column(default=True, server_default="true")

    receta: Mapped[list["RecetaInsumo"]] = relationship(
        back_populates="producto", cascade="all, delete-orphan"
    )


class MateriaPrima(Base):
    __tablename__ = "materias_primas"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), index=True)
    unidad_medida: Mapped[str] = mapped_column(String(20))
    stock_actual: Mapped[Decimal] = mapped_column(Cantidad, default=Decimal("0"))
    stock_minimo: Mapped[Decimal] = mapped_column(
        Cantidad, default=Decimal("0"), server_default="0"
    )
    costo_unitario_actual: Mapped[Decimal] = mapped_column(
        CostoUnitario, default=Decimal("0"), server_default="0"
    )


class RecetaInsumo(Base):
    """Cantidad de una materia prima necesaria para producir UNA unidad de producto."""

    __tablename__ = "recetas_insumos"
    __table_args__ = (UniqueConstraint("producto_id", "materia_prima_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"), index=True)
    materia_prima_id: Mapped[int] = mapped_column(ForeignKey("materias_primas.id"))
    cantidad_necesaria: Mapped[Decimal] = mapped_column(CostoUnitario)

    producto: Mapped[Producto] = relationship(back_populates="receta")
    materia_prima: Mapped[MateriaPrima] = relationship()


class LoteProduccion(Base):
    __tablename__ = "lotes_produccion"

    id: Mapped[int] = mapped_column(primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"), index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    cantidad_producida: Mapped[int]
    fecha_hora: Mapped[datetime] = mapped_column(default=utcnow, index=True)

    producto: Mapped[Producto] = relationship()


class Merma(Base):
    __tablename__ = "mermas"

    id: Mapped[int] = mapped_column(primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"), index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    cantidad_perdida: Mapped[int]
    motivo: Mapped[str] = mapped_column(String(200))
    fecha_hora: Mapped[datetime] = mapped_column(default=utcnow, index=True)

    producto: Mapped[Producto] = relationship()
