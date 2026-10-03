"""Contratos de la autenticación híbrida: PIN, terminales, reautenticación y app móvil."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.models.enums import RolEnum, TipoTerminalEnum
from app.schemas.common import ORMModel
from app.schemas.usuarios import UsuarioOut

Pin = Annotated[str, Field(pattern=r"^\d{4,6}$")]
Nombre80 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


# ---------- Sesión actual ----------


class SesionOut(BaseModel):
    metodo: str                          # pwd | google | pin
    auth_time: datetime                  # última autenticación fuerte (los refresh y el PIN no la renuevan)
    fuerte: bool                         # ¿alcanza hoy para la gestión sensible?
    terminal_id: int | None = None


class MeOut(UsuarioOut):
    sesion: SesionOut


class ReautenticacionIn(BaseModel):
    password: Annotated[str, Field(max_length=72)]


# ---------- PIN y terminales ----------


class PinLoginIn(BaseModel):
    usuario_id: int
    pin: Pin


class PinIn(BaseModel):
    pin: Pin


class UsuarioPinOut(ORMModel):
    id: int
    username: str
    nombre: str | None
    rol: RolEnum


class TerminalCreate(BaseModel):
    nombre: Nombre80
    tipo: TipoTerminalEnum


class TerminalUpdate(BaseModel):
    nombre: Nombre80 | None = None
    activo: bool | None = None


class TerminalOut(ORMModel):
    id: int
    nombre: str
    tipo: TipoTerminalEnum
    activo: bool
    creado_en: datetime
    ultimo_uso: datetime | None


class TerminalActualOut(BaseModel):
    """El equipo desde el que se está entrando y las personas que pueden usar PIN en él."""

    id: int
    nombre: str
    tipo: TipoTerminalEnum
    usuarios: list[UsuarioPinOut]


class MetodosOut(BaseModel):
    """Qué opciones de ingreso ofrece la pantalla de login en este equipo."""

    password: bool = True
    google: bool
    terminal: TerminalActualOut | None


# ---------- App móvil ----------


class DispositivoIn(BaseModel):
    nombre: Nombre80
    plataforma: Annotated[
        str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=1, max_length=20)
    ]


class MovilLoginIn(BaseModel):
    username: Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, max_length=50)]
    password: Annotated[str, Field(max_length=72)]
    dispositivo: DispositivoIn


class MovilGoogleIn(BaseModel):
    id_token: Annotated[str, Field(min_length=20, max_length=4096)]
    nonce: Annotated[str, Field(min_length=8, max_length=128)]
    dispositivo: DispositivoIn


class RefreshIn(BaseModel):
    refresh_token: Annotated[str, Field(min_length=20, max_length=200)]


class MovilReautenticacionIn(BaseModel):
    """Contraseña, o un id_token de Google (con su nonce)."""

    password: Annotated[str, Field(max_length=72)] | None = None
    id_token: Annotated[str, Field(min_length=20, max_length=4096)] | None = None
    nonce: Annotated[str, Field(min_length=8, max_length=128)] | None = None


class SesionMovilOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int                      # segundos de vida del access token
    dispositivo_id: int
    usuario: UsuarioOut


class AccessMovilOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class DispositivoOut(ORMModel):
    id: int
    nombre: str
    plataforma: str
    creado_en: datetime
    ultimo_uso: datetime | None
    revocado_en: datetime | None
