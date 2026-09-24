from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, StringConstraints

# Salidas: Decimal se serializa como número JSON (Pydantic lo haría como string).
DineroOut = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]
CantidadOut = DineroOut

# Entradas validadas
DineroPositivo = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
DineroNoNegativo = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
CantidadInsumo = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=3)]
CantidadInsumoNoNeg = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=3)]
Unidades = Annotated[int, Field(gt=0, le=100_000)]

Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
TextoLargo = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
TextoOpcional = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Mensaje(BaseModel):
    mensaje: str
