from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric
from sqlalchemy.orm import DeclarativeBase


def utcnow() -> datetime:
    return datetime.now(UTC)


# Tipos de columna reutilizables. El dinero nunca se guarda como float.
Dinero = Numeric(12, 2)
Cantidad = Numeric(12, 3)  # insumos: kg, litros, unidades fraccionadas
CostoUnitario = Numeric(14, 4)
FechaHora = DateTime(timezone=True)


class Base(DeclarativeBase):
    type_annotation_map = {Decimal: Dinero, datetime: FechaHora}
