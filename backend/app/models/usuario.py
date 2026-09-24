from datetime import datetime

from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow
from app.models.enums import RolEnum


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    nombre: Mapped[str | None] = mapped_column(String(100))
    rol: Mapped[RolEnum] = mapped_column(Enum(RolEnum))
    hashed_password: Mapped[str] = mapped_column(String(255))
    activo: Mapped[bool] = mapped_column(default=True, server_default="true")
    # Se incrementa al cambiar la contraseña o desactivar al usuario:
    # invalida todos los tokens emitidos antes.
    token_version: Mapped[int] = mapped_column(default=0, server_default="0")
    creado_en: Mapped[datetime] = mapped_column(default=utcnow)
