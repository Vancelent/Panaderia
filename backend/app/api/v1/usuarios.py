from fastapi import APIRouter, status

from app.api.deps import DB, Admin
from app.schemas.usuarios import UsuarioAdminOut, UsuarioCreate, UsuarioUpdate
from app.services import usuarios as svc

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])


@router.get("", response_model=list[UsuarioAdminOut])
def listar(_: Admin, db: DB):
    return svc.listar(db)


@router.post("", response_model=UsuarioAdminOut, status_code=status.HTTP_201_CREATED)
def crear(datos: UsuarioCreate, _: Admin, db: DB):
    return svc.crear(db, datos)


@router.patch("/{usuario_id}", response_model=UsuarioAdminOut)
def actualizar(usuario_id: int, datos: UsuarioUpdate, actor: Admin, db: DB):
    return svc.actualizar(db, usuario_id, datos, actor)
