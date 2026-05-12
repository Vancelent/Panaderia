from pydantic import BaseModel, ConfigDict
from datetime import datetime

class TurnoCreate(BaseModel):
    user_id: int
    fondo_fijo: float

class TurnoResponse(BaseModel):
    id: int
    user_id: int
    fondo_fijo: float
    fecha_apertura: datetime
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

class TurnoCerrar(BaseModel):
    turno_id: int
    monto_declarado: float

class MensajeCierre(BaseModel):
    message: str
    turno_id: int
