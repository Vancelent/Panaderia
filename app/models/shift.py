from typing import Optional
from datetime import datetime, timezone
from sqlalchemy import ForeignKey, DateTime, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class Turno(Base):
    __tablename__ = "turnos"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    fondo_fijo: Mapped[float] = mapped_column(Float, nullable=False)
    fecha_apertura: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    fecha_cierre: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)

    # Relaciones
    user = relationship("User", lazy="selectin")
    arqueo = relationship("Arqueo", back_populates="turno", uselist=False, lazy="selectin")

class Arqueo(Base):
    __tablename__ = "arqueos"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    turno_id: Mapped[int] = mapped_column(ForeignKey("turnos.id"), unique=True)
    
    # El monto calculado por el sistema (Fondo fijo + ventas)
    monto_sistema: Mapped[float] = mapped_column(Float, nullable=False)
    # El monto físico que contó la vendedora
    monto_declarado: Mapped[float] = mapped_column(Float, nullable=False)
    # Diferencia oculta
    diferencia: Mapped[float] = mapped_column(Float, nullable=False)

    turno = relationship("Turno", back_populates="arqueo", lazy="selectin")
