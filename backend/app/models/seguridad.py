"""Identidades externas (Google), terminales con PIN y sesiones de la app móvil (docs/rfc-001 §2 y §8.3)."""

import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow
from app.models.enums import ProveedorIdentidadEnum, TipoTerminalEnum
from app.models.usuario import Usuario


class IdentidadExterna(Base):
    """Cuenta de Google vinculada a un usuario. Se busca por `sub` (estable), no por el correo."""

    __tablename__ = "identidades_externas"
    __table_args__ = (UniqueConstraint("proveedor", "sub"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    proveedor: Mapped[ProveedorIdentidadEnum] = mapped_column(Enum(ProveedorIdentidadEnum))
    sub: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(120))
    creado_en: Mapped[datetime] = mapped_column(default=utcnow)
    ultimo_uso: Mapped[datetime | None]

    usuario: Mapped[Usuario] = relationship(back_populates="identidades")


class Terminal(Base):
    """Equipo registrado donde se puede entrar con PIN. Solo se guarda el hash del secreto que vive
    en su cookie: una copia de la base no permite hacerse pasar por la caja."""

    __tablename__ = "terminales"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80))
    tipo: Mapped[TipoTerminalEnum] = mapped_column(Enum(TipoTerminalEnum))
    secreto_hash: Mapped[str] = mapped_column(String(64), unique=True)
    activo: Mapped[bool] = mapped_column(default=True, server_default="true")
    creado_por_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = mapped_column(default=utcnow)
    ultimo_uso: Mapped[datetime | None]

    creado_por: Mapped[Usuario] = relationship()


class Dispositivo(Base):
    """Celular donde se inició sesión en la app. Revocarlo cierra todas sus sesiones."""

    __tablename__ = "dispositivos"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(80))
    plataforma: Mapped[str] = mapped_column(String(20))
    creado_en: Mapped[datetime] = mapped_column(default=utcnow)
    ultimo_uso: Mapped[datetime | None]
    revocado_en: Mapped[datetime | None]

    usuario: Mapped[Usuario] = relationship()


class RefreshToken(Base):
    """Token de renovación opaco (256 bits). En la base solo vive su SHA-256.

    Cada uso lo rota. Reutilizar uno ya usado fuera de la ventana de gracia revoca toda la
    familia: alguien más tiene una copia.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    dispositivo_id: Mapped[int] = mapped_column(ForeignKey("dispositivos.id"), index=True)
    familia_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    emitido_en: Mapped[datetime] = mapped_column(default=utcnow)
    expira_en: Mapped[datetime]
    usado_en: Mapped[datetime | None]
    reemplazado_por_id: Mapped[int | None] = mapped_column(ForeignKey("refresh_tokens.id"))
    revocado_en: Mapped[datetime | None]
    # El refresh no renueva estos datos: la reautenticación para gestión sensible la pide de nuevo
    metodo: Mapped[str] = mapped_column(String(10))
    auth_time: Mapped[datetime]

    dispositivo: Mapped[Dispositivo] = relationship()
