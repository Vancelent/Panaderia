from decimal import Decimal
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.models.enums import MetodoPagoEnum


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
    # "__Host-" en producción: el navegador solo acepta esa cookie si es Secure, sin Domain y con
    # Path=/, lo que bloquea el "cookie tossing" desde subdominios (docs/rfc-001 D7). Se antepone
    # al nombre de las cookies de sesión y CSRF; el frontend las busca con o sin el prefijo.
    cookie_prefix: Literal["", "__Host-"] = ""
    csrf_header_name: str = "X-CSRF-Token"
    # En producción detrás de HTTPS debe ser True.
    cookie_secure: bool = False

    # Orígenes permitidos para CORS, separados por coma. Con el proxy de Vite
    # el frontend es same-origin y esta lista puede quedar vacía.
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # Zona horaria del local: define qué es "hoy" en reportes y agrupaciones diarias.
    zona_horaria: str = "America/Argentina/Buenos_Aires"

    # Medios que muestra la caja (nombres del enum, separados por coma). La cuenta corriente
    # no se lista acá: se ofrece siempre que la venta tenga un cliente.
    medios_pago_habilitados: Annotated[list[MetodoPagoEnum], NoDecode] = Field(
        default_factory=lambda: [
            MetodoPagoEnum.EFECTIVO,
            MetodoPagoEnum.TRANSFERENCIA,
            MetodoPagoEnum.TARJETA,
        ]
    )

    # Punto de partida del reparto (la panadería). Sin esto, la ruta sugerida arranca desde el
    # centro de los puntos a visitar.
    panaderia_latitud: Decimal | None = None
    panaderia_longitud: Decimal | None = None
    # La traza GPS cruda se conserva este tiempo (particiones mensuales; ver docs/rfc-001 §5.4)
    retencion_gps_dias: int = Field(default=90, ge=7, le=3650)
    # Una entrega confirmada a más de esta distancia del punto cargado se marca como alerta
    alerta_distancia_entrega_m: int = Field(default=300, ge=50, le=5000)

    # Conexiones a la base por proceso (pool + desborde). Con 1 worker y `max_connections=15` en
    # Postgres, 4 + 2 deja margen para mantenimiento y para `psql`. Solo aplica a PostgreSQL.
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_max_overflow: int = Field(default=10, ge=0, le=50)

    login_max_intentos: int = 5
    login_ventana_segundos: int = 300

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @field_validator("panaderia_latitud", "panaderia_longitud", mode="before")
    @classmethod
    def _coordenada_vacia(cls, v):
        # Copiar .env.example deja "PANADERIA_LATITUD=": se toma como "sin configurar"
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("medios_pago_habilitados", mode="before")
    @classmethod
    def _parsear_medios(cls, v):
        # Acepta "EFECTIVO,TRANSFERENCIA" (nombres del enum, sin importar mayúsculas)
        if isinstance(v, str):
            nombres = [n.strip().upper() for n in v.split(",") if n.strip()]
            try:
                return [MetodoPagoEnum[n] for n in nombres]
            except KeyError as e:
                validos = ", ".join(m.name for m in MetodoPagoEnum)
                raise ValueError(f"Medio de pago desconocido {e}. Válidos: {validos}") from None
        return v

    @model_validator(mode="after")
    def _prefijo_de_cookies(self):
        if self.cookie_prefix == "__Host-":
            if not self.cookie_secure:
                raise ValueError(
                    "COOKIE_PREFIX=__Host- exige COOKIE_SECURE=true (el navegador rechaza la cookie)."
                )
            if not self.cookie_name.startswith("__Host-"):
                self.cookie_name = f"__Host-{self.cookie_name}"
            if not self.csrf_cookie_name.startswith("__Host-"):
                self.csrf_cookie_name = f"__Host-{self.csrf_cookie_name}"
        return self

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
