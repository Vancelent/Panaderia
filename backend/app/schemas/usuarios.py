from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field, StringConstraints

from app.models.enums import RolEnum
from app.schemas.common import ORMModel


def _normalizar(v):
    return v.strip().lower() if isinstance(v, str) else v


Username = Annotated[
    str,
    BeforeValidator(_normalizar),
    StringConstraints(min_length=3, max_length=50, pattern=r"^[a-z0-9._-]+$"),
]
# bcrypt usa como máximo 72 bytes
Password = Annotated[str, Field(min_length=8, max_length=72)]


class LoginIn(BaseModel):
    username: Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, max_length=50)]
    password: Annotated[str, Field(max_length=72)]


class UsuarioOut(ORMModel):
    id: int
    username: str
    nombre: str | None
    rol: RolEnum
    activo: bool


class UsuarioAdminOut(UsuarioOut):
    creado_en: datetime | None


class UsuarioCreate(BaseModel):
    username: Username
    nombre: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None = None
    rol: RolEnum
    password: Password


class UsuarioUpdate(BaseModel):
    nombre: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None = None
    rol: RolEnum | None = None
    activo: bool | None = None
    password: Password | None = None


class CambioPassword(BaseModel):
    password_actual: Annotated[str, Field(max_length=72)]
    password_nueva: Password
