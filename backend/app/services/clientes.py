from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import Cliente
from app.schemas.comercial import ClienteCreate, ClienteUpdate


def listar(db: Session, *, buscar: str | None = None, incluir_inactivos: bool = False) -> list[Cliente]:
    q = select(Cliente).order_by(Cliente.nombre)
    if not incluir_inactivos:
        q = q.where(Cliente.activo.is_(True))
    if buscar:
        # Parámetro enlazado por SQLAlchemy: no hay riesgo de inyección
        patron = f"%{buscar.strip()}%"
        q = q.where(or_(Cliente.nombre.ilike(patron), Cliente.telefono.ilike(patron)))
    return list(db.scalars(q.limit(200)))


def obtener(db: Session, cliente_id: int) -> Cliente:
    cliente = db.get(Cliente, cliente_id)
    if cliente is None:
        raise NotFoundError("Cliente no encontrado.")
    return cliente


def crear(db: Session, datos: ClienteCreate) -> Cliente:
    cliente = Cliente(**datos.model_dump())
    db.add(cliente)
    db.commit()
    return cliente


def actualizar(db: Session, cliente_id: int, datos: ClienteUpdate) -> Cliente:
    cliente = obtener(db, cliente_id)
    cambios = datos.model_dump(exclude_unset=True)
    if cambios.get("nombre") is None:
        cambios.pop("nombre", None)
    if cambios.get("activo") is None:
        cambios.pop("activo", None)
    for campo, valor in cambios.items():
        setattr(cliente, campo, valor)
    db.commit()
    return cliente
