from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración leída de variables de entorno (o de un archivo .env).

    Los secretos no tienen valor por defecto: si faltan, la app no arranca.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: Literal["development", "production", "test"] = "development"

    database_url: str
    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    jwt_expire_minutes: int = Field(default=480, ge=5, le=24 * 60)

    cookie_name: str = "panaderia_session"
    csrf_cookie_name: str = "panaderia_csrf"
    csrf_header_name: str = "X-CSRF-Token"
    # En producción detrás de HTTPS debe ser True.
    cookie_secure: bool = False

    # Orígenes permitidos para CORS, separados por coma. Con el proxy de Vite
    # el frontend es same-origin y esta lista puede quedar vacía.
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # Zona horaria del local: define qué es "hoy" en reportes y agrupaciones diarias.
    zona_horaria: str = "America/Argentina/Buenos_Aires"

    login_max_intentos: int = 5
    login_ventana_segundos: int = 300

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @field_validator("database_url")
    @classmethod
    def _normalizar_driver(cls, v: str) -> str:
        # Aceptamos la URL "postgresql://" clásica y la pasamos al driver psycopg 3.
        if v.startswith("postgresql://"):
            return "postgresql+psycopg://" + v.removeprefix("postgresql://")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
