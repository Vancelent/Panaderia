import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow


class Numerador(Base):
    """Contador sin huecos (p. ej. el número de remito). Se incrementa bajo FOR UPDATE."""

    __tablename__ = "numeradores"

    tipo: Mapped[str] = mapped_column(String(20), primary_key=True)
    ultimo_numero: Mapped[int] = mapped_column(default=0)


class OperacionIdempotente(Base):
    """Operaciones de la app móvil ya aplicadas. Reenviar una operación devuelve la respuesta
    guardada en lugar de repetirla (la clave es un UUID generado en el dispositivo)."""

    __tablename__ = "operaciones_idempotentes"

    operacion_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    tipo: Mapped[str] = mapped_column(String(40))
    respuesta: Mapped[Any | None] = mapped_column(JSON)
    creado_en: Mapped[datetime] = mapped_column(default=utcnow, index=True)
