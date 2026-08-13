import enum
from datetime import datetime, timezone
from sqlalchemy import Integer, String, Float, ForeignKey, DateTime, Boolean, Enum as SQLAlchemyEnum
from sqlalchemy.orm import relationship, Mapped, mapped_column
from database import Base

# --- Enums para roles y estados ---
class RolEnum(str, enum.Enum):
    ADMIN = "Admin"
    ENCARGADA = "Encargada"
    VENDEDORA = "Vendedora"
    PANADERO = "Panadero"

class EstadoTurnoEnum(str, enum.Enum):
    ABIERTO = "Abierto"
    CERRADO = "Cerrado"

class MetodoPagoEnum(str, enum.Enum):
    EFECTIVO = "Efectivo"
    TARJETA = "Tarjeta"
    TRANSFERENCIA = "Transferencia"

# --- Modelos (Tablas de BD) ---
class Usuario(Base):
    __tablename__ = "usuarios"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    rol: Mapped[RolEnum] = mapped_column(SQLAlchemyEnum(RolEnum), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)

    turnos = relationship("Turno", back_populates="usuario")

class Turno(Base):
    __tablename__ = "turnos"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    
    fecha_apertura: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    efectivo_inicial: Mapped[float] = mapped_column(Float, nullable=False)
    fecha_cierre: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    estado: Mapped[EstadoTurnoEnum] = mapped_column(SQLAlchemyEnum(EstadoTurnoEnum), default=EstadoTurnoEnum.ABIERTO)
    
    usuario = relationship("Usuario", back_populates="turnos")
    arqueo = relationship("Arqueo", back_populates="turno", uselist=False)
    ventas = relationship("Venta", back_populates="turno")

class Venta(Base):
    __tablename__ = "ventas"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    turno_id: Mapped[int] = mapped_column(ForeignKey("turnos.id"), nullable=False)
    monto: Mapped[float] = mapped_column(Float, nullable=False)
    metodo_pago: Mapped[MetodoPagoEnum] = mapped_column(SQLAlchemyEnum(MetodoPagoEnum), default=MetodoPagoEnum.EFECTIVO)

    turno = relationship("Turno", back_populates="ventas")
    detalles = relationship("DetalleVenta", back_populates="venta")

class Producto(Base):
    __tablename__ = "productos"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    nombre: Mapped[str] = mapped_column(String, index=True, nullable=False)
    precio_venta: Mapped[float] = mapped_column(Float, nullable=False)
    stock_mostrador: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    detalles = relationship("DetalleVenta", back_populates="producto")
    recetas = relationship("RecetaInsumo", back_populates="producto")

class MateriaPrima(Base):
    __tablename__ = "materias_primas"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    nombre: Mapped[str] = mapped_column(String, index=True, nullable=False)
    stock_actual_kg: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    unidad_medida: Mapped[str] = mapped_column(String, nullable=False)
    costo_unitario_actual: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    recetas = relationship("RecetaInsumo", back_populates="materia_prima")
    compras = relationship("CompraMateriaPrima", back_populates="materia_prima")

class RecetaInsumo(Base):
    __tablename__ = "recetas_insumos"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"), nullable=False)
    materia_prima_id: Mapped[int] = mapped_column(ForeignKey("materias_primas.id"), nullable=False)
    cantidad_necesaria: Mapped[float] = mapped_column(Float, nullable=False)

    producto = relationship("Producto", back_populates="recetas")
    materia_prima = relationship("MateriaPrima", back_populates="recetas")

class DetalleVenta(Base):
    __tablename__ = "detalles_venta"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    venta_id: Mapped[int] = mapped_column(ForeignKey("ventas.id"), nullable=False)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"), nullable=False)
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False)
    subtotal: Mapped[float] = mapped_column(Float, nullable=False)

    venta = relationship("Venta", back_populates="detalles")
    producto = relationship("Producto", back_populates="detalles")

class Arqueo(Base):
    __tablename__ = "arqueos"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    turno_id: Mapped[int] = mapped_column(ForeignKey("turnos.id"), unique=True, nullable=False)
    
    monto_sistema: Mapped[float] = mapped_column(Float, nullable=False)
    monto_declarado: Mapped[float] = mapped_column(Float, nullable=False)
    diferencia: Mapped[float] = mapped_column(Float, nullable=False)

    turno = relationship("Turno", back_populates="arqueo")

class LoteProduccion(Base):
    __tablename__ = "lotes_produccion"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"), nullable=False)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    cantidad_producida: Mapped[int] = mapped_column(Integer, nullable=False)
    fecha_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    producto = relationship("Producto")
    usuario = relationship("Usuario")

class Merma(Base):
    __tablename__ = "mermas"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"), nullable=False)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    cantidad_perdida: Mapped[int] = mapped_column(Integer, nullable=False)
    motivo: Mapped[str] = mapped_column(String, nullable=False)
    fecha_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    producto = relationship("Producto")
    usuario = relationship("Usuario")

class Proveedor(Base):
    __tablename__ = "proveedores"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    nombre: Mapped[str] = mapped_column(String, index=True, nullable=False)
    cuit: Mapped[str] = mapped_column(String, nullable=True)
    telefono: Mapped[str] = mapped_column(String, nullable=True)
    direccion: Mapped[str] = mapped_column(String, nullable=True)
    notas: Mapped[str] = mapped_column(String, nullable=True)

    compras = relationship("CompraMateriaPrima", back_populates="proveedor")

class CompraMateriaPrima(Base):
    __tablename__ = "compras_materias_primas"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    proveedor_id: Mapped[int] = mapped_column(ForeignKey("proveedores.id"), nullable=False)
    materia_prima_id: Mapped[int] = mapped_column(ForeignKey("materias_primas.id"), nullable=False)
    cantidad_comprada: Mapped[float] = mapped_column(Float, nullable=False)
    precio_total: Mapped[float] = mapped_column(Float, nullable=False)
    metodo_pago: Mapped[MetodoPagoEnum] = mapped_column(SQLAlchemyEnum(MetodoPagoEnum), default=MetodoPagoEnum.EFECTIVO)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    proveedor = relationship("Proveedor", back_populates="compras")
    materia_prima = relationship("MateriaPrima", back_populates="compras")

class GastoVario(Base):
    __tablename__ = "gastos_varios"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    concepto: Mapped[str] = mapped_column(String, nullable=False)
    monto: Mapped[float] = mapped_column(Float, nullable=False)
    metodo_pago: Mapped[MetodoPagoEnum] = mapped_column(SQLAlchemyEnum(MetodoPagoEnum), default=MetodoPagoEnum.EFECTIVO)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class AuditoriaInventario(Base):
    __tablename__ = "auditorias_inventario"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    materia_prima_id: Mapped[int] = mapped_column(ForeignKey("materias_primas.id"), nullable=False)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    stock_teorico: Mapped[float] = mapped_column(Float, nullable=False)
    stock_real: Mapped[float] = mapped_column(Float, nullable=False)
    diferencia: Mapped[float] = mapped_column(Float, nullable=False)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    materia_prima = relationship("MateriaPrima")
    usuario = relationship("Usuario")

class HistorialPrecio(Base):
    __tablename__ = "historial_precios"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"), nullable=False)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    precio_anterior: Mapped[float] = mapped_column(Float, nullable=False)
    precio_nuevo: Mapped[float] = mapped_column(Float, nullable=False)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    producto = relationship("Producto")
    usuario = relationship("Usuario")
