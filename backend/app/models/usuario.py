from datetime import datetime

from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
    # Correo (en minúsculas) con el que un admin vincula la cuenta de Google de la persona
    email: Mapped[str | None] = mapped_column(String(120), unique=True)
    # bcrypt de un HMAC del PIN (ver core/security.py): una copia de la base no revela los PIN
    pin_hash: Mapped[str | None] = mapped_column(String(255))
    pin_fallidos: Mapped[int] = mapped_column(default=0, server_default="0")
    pin_bloqueado: Mapped[bool] = mapped_column(default=False, server_default="false")

    identidades: Mapped[list["IdentidadExterna"]] = relationship(  # noqa: F821
        back_populates="usuario", cascade="all, delete-orphan"
    )

    @property
    def tiene_pin(self) -> bool:
        return self.pin_hash is not None

    @property
    def google_vinculado(self) -> bool:
        return bool(self.identidades)
