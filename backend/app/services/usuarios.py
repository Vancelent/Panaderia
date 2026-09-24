from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AuthError, ConflictError, NotFoundError
from app.core.security import hash_password, verify_password, verify_password_dummy
from app.models import RolEnum, Usuario
from app.schemas.usuarios import UsuarioCreate, UsuarioUpdate


def autenticar(db: Session, username: str, password: str) -> Usuario:
    usuario = db.scalar(select(Usuario).where(Usuario.username == username))
    if usuario is None:
        verify_password_dummy(password)
        raise AuthError("Usuario o contraseña incorrectos.", code="invalid_credentials")
    if not verify_password(password, usuario.hashed_password) or not usuario.activo:
        raise AuthError("Usuario o contraseña incorrectos.", code="invalid_credentials")
    return usuario


def listar(db: Session) -> list[Usuario]:
    return list(db.scalars(select(Usuario).order_by(Usuario.username)))


def obtener(db: Session, usuario_id: int) -> Usuario:
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise NotFoundError("Usuario no encontrado.")
    return usuario


def crear(db: Session, datos: UsuarioCreate) -> Usuario:
    if db.scalar(select(Usuario.id).where(Usuario.username == datos.username)):
        raise ConflictError("Ya existe un usuario con ese nombre.", code="username_taken")
    usuario = Usuario(
        username=datos.username,
        nombre=datos.nombre,
        rol=datos.rol,
        hashed_password=hash_password(datos.password),
    )
    db.add(usuario)
    db.commit()
    return usuario


def _hay_otro_admin_activo(db: Session, excepto_id: int) -> bool:
    return (
        db.scalar(
            select(Usuario.id).where(
                Usuario.rol == RolEnum.ADMIN, Usuario.activo.is_(True), Usuario.id != excepto_id
            )
        )
        is not None
    )


def actualizar(db: Session, usuario_id: int, datos: UsuarioUpdate, actor: Usuario) -> Usuario:
    usuario = obtener(db, usuario_id)
    cambios = datos.model_dump(exclude_unset=True)

    pierde_admin = usuario.rol == RolEnum.ADMIN and (
        (cambios.get("rol") or RolEnum.ADMIN) != RolEnum.ADMIN or cambios.get("activo") is False
    )
    if pierde_admin and not _hay_otro_admin_activo(db, usuario.id):
        raise ConflictError("Debe quedar al menos un administrador activo.")
    if usuario.id == actor.id and cambios.get("activo") is False:
        raise ConflictError("No podés desactivar tu propio usuario.")

    if "password" in cambios:
        password = cambios.pop("password")
        if password:
            usuario.hashed_password = hash_password(password)
            usuario.token_version += 1
    if cambios.get("activo") is False or cambios.get("rol") not in (None, usuario.rol):
        # Cierra las sesiones abiertas del usuario
        usuario.token_version += 1
    for campo, valor in cambios.items():
        if valor is not None:
            setattr(usuario, campo, valor)
    db.commit()
    return usuario


def cambiar_password(db: Session, usuario: Usuario, actual: str, nueva: str) -> Usuario:
    if not verify_password(actual, usuario.hashed_password):
        raise AuthError("La contraseña actual no es correcta.", code="invalid_credentials")
    usuario.hashed_password = hash_password(nueva)
    usuario.token_version += 1
    db.commit()
    return usuario


def cerrar_sesiones(db: Session, usuario: Usuario) -> None:
    usuario.token_version += 1
    db.commit()
