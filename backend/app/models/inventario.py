from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Cantidad, CostoUnitario, utcnow


class Producto(Base):
    __tablename__ = "productos"
    __table_args__ = (
        # La base garantiza que no se reserve más de lo que hay en el mostrador.
        CheckConstraint(
            "stock_reservado >= 0 AND stock_reservado <= stock_mostrador",
            name="ck_productos_reserva_valida",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), index=True)
    categoria: Mapped[str | None] = mapped_column(String(60))
    # Carga rápida por código (teclado o lector de códigos de barras)
    codigo: Mapped[str | None] = mapped_column(String(12), unique=True)
    precio_venta: Mapped[Decimal]
    stock_mostrador: Mapped[int] = mapped_column(default=0)
    # Unidades comprometidas en hojas de ruta confirmadas (las usa el reparto, Fase 2).
    # Disponible para la caja = stock_mostrador - stock_reservado.
    stock_reservado: Mapped[int] = mapped_column(default=0, server_default="0")
    stock_minimo: Mapped[int] = mapped_column(default=0, server_default="0")
    activo: Mapped[bool] = mapped_column(default=True, server_default="true")
    # Variante "día anterior": apunta al producto fresco del que sale. Una por producto.
    producto_base_id: Mapped[int | None] = mapped_column(ForeignKey("productos.id"), unique=True)

    @property
    def stock_disponible(self) -> int:
        return self.stock_mostrador - self.stock_reservado

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


class ConversionDiaAnterior(Base):
    """Ajuste manual de la encargada: unidades que pasan del producto fresco a su variante
    "día anterior". Un registro por producto y operación; nunca se edita ni se borra.

    Una reversión es otra fila con `revierte_id` apuntando a la original (mismas
    unidades, en sentido contrario). Solo se puede revertir una vez.
    """

    __tablename__ = "conversiones_dia_anterior"
    __table_args__ = (CheckConstraint("cantidad > 0", name="ck_conversion_cantidad_positiva"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    producto_base_id: Mapped[int] = mapped_column(ForeignKey("productos.id"), index=True)
    variante_id: Mapped[int] = mapped_column(ForeignKey("productos.id"))
    cantidad: Mapped[int]
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    fecha: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    motivo: Mapped[str | None] = mapped_column(String(200))
    revierte_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversiones_dia_anterior.id"), unique=True
    )

    producto_base: Mapped[Producto] = relationship(foreign_keys=[producto_base_id])
    variante: Mapped[Producto] = relationship(foreign_keys=[variante_id])
