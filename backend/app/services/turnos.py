"""Bloqueo del turno para toda operación que agrega dinero a su arqueo.

Es el nivel 2 de la jerarquía de bloqueos (ver docs/rfc-001). `FOR SHARE` es compatible
entre ventas y cobros (no se frenan entre sí) pero incompatible con el `FOR UPDATE` del
cierre: el arqueo espera a que terminen las operaciones en curso y ninguna queda fuera.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models import EstadoTurnoEnum, Turno


def bloquear_para_cobro(db: Session, turno_id: int) -> Turno:
    """Toma FOR SHARE sobre el turno y verifica que siga abierto.

    `populate_existing` es clave: el turno puede estar ya cargado en la sesión como
    ABIERTO y haberse cerrado en otra transacción después.
    """
    turno = db.scalar(
        select(Turno)
        .where(Turno.id == turno_id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    if turno is None:
        raise NotFoundError("Turno no encontrado.")
    if turno.estado != EstadoTurnoEnum.ABIERTO:
        raise ConflictError("El turno ya fue cerrado.", code="turno_cerrado")
    return turno
