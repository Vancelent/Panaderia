from typing import Any

from sqlalchemy import Table
from sqlalchemy.orm import Session


def insertar_nuevos(db: Session, tabla: Table, valores: dict[str, Any] | list[dict[str, Any]]) -> int:
    """INSERT ... ON CONFLICT DO NOTHING, en PostgreSQL y en SQLite (los tests).

    Devuelve cuántas filas se insertaron de verdad: las repetidas no cuentan. Se cuentan con
    `RETURNING` porque `rowcount` no es confiable en este tipo de INSERT (psycopg informa -1).
    """
    dialecto = db.get_bind().dialect.name
    if dialecto == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialecto == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:  # pragma: no cover
        raise NotImplementedError(f"Dialecto no soportado: {dialecto}")
    sentencia = (
        insert(tabla).values(valores).on_conflict_do_nothing().returning(*tabla.primary_key.columns)
    )
    return len(db.execute(sentencia).all())
