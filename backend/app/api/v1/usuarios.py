from fastapi import APIRouter, status

from app.api.deps import DB, Admin, AdminFuerte
from app.schemas.auth import DispositivoOut, PinIn
from app.schemas.common import Mensaje
from app.schemas.usuarios import UsuarioAdminOut, UsuarioCreate, UsuarioUpdate
from app.services import google, sesiones_moviles, terminales
from app.services import usuarios as svc

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])

# La gestión de usuarios es gestión sensible (docs/rfc-001 §2.4): contraseña o Google, iniciada hace
# poco. Solo el listado, que no cambia nada, queda con el rol a secas.


@router.get("", response_model=list[UsuarioAdminOut])
def listar(_: Admin, db: DB):
    return svc.listar(db)


@router.post("", response_model=UsuarioAdminOut, status_code=status.HTTP_201_CREATED)
def crear(datos: UsuarioCreate, _: AdminFuerte, db: DB):
    return svc.crear(db, datos)


@router.patch("/{usuario_id}", response_model=UsuarioAdminOut)
def actualizar(usuario_id: int, datos: UsuarioUpdate, actor: AdminFuerte, db: DB):
    return svc.actualizar(db, usuario_id, datos, actor)


# ---------- PIN ----------


@router.put("/{usuario_id}/pin", response_model=UsuarioAdminOut)
def establecer_pin(usuario_id: int, datos: PinIn, _: AdminFuerte, db: DB):
    """Fija o cambia el PIN (4 a 6 dígitos). Desbloquea el PIN y cierra las sesiones abiertas del usuario."""
    return terminales.establecer_pin(db, svc.obtener(db, usuario_id), datos.pin)


@router.delete("/{usuario_id}/pin", response_model=UsuarioAdminOut)
def quitar_pin(usuario_id: int, _: AdminFuerte, db: DB):
    return terminales.quitar_pin(db, svc.obtener(db, usuario_id))


@router.post("/{usuario_id}/pin/desbloqueo", response_model=UsuarioAdminOut)
def desbloquear_pin(usuario_id: int, _: AdminFuerte, db: DB):
    usuario = svc.obtener(db, usuario_id)
    terminales.desbloquear_pin(usuario)
    db.commit()
    return usuario


# ---------- Google ----------


@router.delete("/{usuario_id}/google", response_model=UsuarioAdminOut)
def desvincular_google(usuario_id: int, _: AdminFuerte, db: DB):
    """Quita la cuenta de Google vinculada. La persona puede volver a vincular otra con su correo."""
    usuario = svc.obtener(db, usuario_id)
    google.desvincular(db, usuario)
    return usuario


# ---------- Dispositivos (app móvil) ----------


@router.get("/{usuario_id}/dispositivos", response_model=list[DispositivoOut])
def dispositivos(usuario_id: int, _: Admin, db: DB):
    svc.obtener(db, usuario_id)
    return sesiones_moviles.listar(db, usuario_id)


@router.delete("/{usuario_id}/dispositivos/{dispositivo_id}", response_model=Mensaje)
def revocar_dispositivo(usuario_id: int, dispositivo_id: int, _: AdminFuerte, db: DB):
    """Cierra todas las sesiones de ese celular en el acto."""
    sesiones_moviles.revocar(db, dispositivo_id, usuario_id=usuario_id)
    return {"mensaje": "Dispositivo revocado."}
