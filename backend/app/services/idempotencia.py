"""Idempotencia de las operaciones de la app móvil (nivel 1 de la jerarquía de bloqueos).

La app genera un UUID por operación y lo reenvía idéntico en cada reintento. El primer intento
reserva la clave con un INSERT; los siguientes encuentran la respuesta que quedó guardada y la
devuelven sin repetir nada. En PostgreSQL, dos reintentos simultáneos se serializan solos: el
segundo INSERT espera a que el primero confirme y recién ahí ve la fila.
"""

from uuid import UUID

from fastapi.encoders import jsonable_encoder
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.db.base import utcnow
from app.db.utils import insertar_nuevos
from app.models import OperacionIdempotente, Usuario


def iniciar(db: Session, operacion_id: UUID, usuario: Usuario, tipo: str) -> dict | None:
    """Reserva la clave. Devuelve None si la operación es nueva, o la respuesta ya guardada
    si es un reintento de una operación completada."""
    reservada = insertar_nuevos(
        db, OperacionIdempotente.__table__,
        {"operacion_id": operacion_id, "usuario_id": usuario.id, "tipo": tipo, "respuesta": None,
         "creado_en": utcnow()},
    )
    if reservada:
        return None

    previa = db.get(OperacionIdempotente, operacion_id, populate_existing=True)
    if previa.usuario_id != usuario.id or previa.tipo != tipo:
        raise ConflictError(
            "Ese identificador de operación ya se usó en otra operación.", code="operacion_en_curso"
        )
    if previa.respuesta is None:
        raise ConflictError("La operación todavía se está procesando.", code="operacion_en_curso")
    return previa.respuesta


def completar(db: Session, operacion_id: UUID, respuesta: dict) -> dict:
    """Guarda la respuesta (en la misma transacción que la operación) y la devuelve serializable."""
    serializable = jsonable_encoder(respuesta)
    db.execute(
        update(OperacionIdempotente)
        .where(OperacionIdempotente.operacion_id == operacion_id)
        .values(respuesta=serializable)
    )
    return serializable
