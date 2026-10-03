from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AuthError, ConflictError, NotFoundError
from app.core.security import hash_password, verify_password, verify_password_dummy
from app.models import RolEnum, Usuario
from app.schemas.usuarios import UsuarioCreate, UsuarioUpdate
from app.services import sesiones_moviles, terminales


def autenticar(db: Session, username: str, password: str) -> Usuario:
    usuario = db.scalar(select(Usuario).where(Usuario.username == username))
    if usuario is None:
        verify_password_dummy(password)
        raise AuthError("Usuario o contraseña incorrectos.", code="invalid_credentials")
    if not verify_password(password, usuario.hashed_password) or not usuario.activo:
        raise AuthError("Usuario o contraseña incorrectos.", code="invalid_credentials")
    liberar_pin(db, usuario)
    return usuario


def _invalidar_sesiones(db: Session, usuario: Usuario) -> None:
    """Corta las sesiones web (token_version) y las de la app (dispositivos y refresh)."""
    usuario.token_version += 1
    sesiones_moviles.revocar_todos(db, usuario.id)


def liberar_pin(db: Session, usuario: Usuario) -> None:
    """Entrar con contraseña o Google confirma la identidad: se libera un PIN bloqueado."""
    if usuario.pin_bloqueado or usuario.pin_fallidos:
        terminales.desbloquear_pin(usuario)
        db.commit()


def listar(db: Session) -> list[Usuario]:
    return list(db.scalars(select(Usuario).order_by(Usuario.username)))


def obtener(db: Session, usuario_id: int) -> Usuario:
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise NotFoundError("Usuario no encontrado.")
    return usuario


def _validar_email_libre(db: Session, email: str | None, excepto_id: int | None = None) -> None:
    if email is None:
        return
    otro = db.scalar(select(Usuario.id).where(Usuario.email == email))
    if otro is not None and otro != excepto_id:
        raise ConflictError("Ese correo ya está asignado a otro usuario.", code="email_en_uso")


def crear(db: Session, datos: UsuarioCreate) -> Usuario:
    if db.scalar(select(Usuario.id).where(Usuario.username == datos.username)):
        raise ConflictError("Ya existe un usuario con ese nombre.", code="username_taken")
    _validar_email_libre(db, datos.email)
    usuario = Usuario(
        username=datos.username,
        nombre=datos.nombre,
        email=datos.email,
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

    if "email" in cambios:
        # Con `null` se quita el correo; por eso no pasa por el filtro de valores nulos de más abajo
        email = cambios.pop("email")
        _validar_email_libre(db, email, usuario.id)
        usuario.email = email
    if cambios.get("rol") not in (None, usuario.rol) and cambios["rol"] not in terminales.ROLES_CON_PIN:
        # Un rol que no usa PIN no puede conservarlo
        usuario.pin_hash, usuario.pin_fallidos, usuario.pin_bloqueado = None, 0, False
    if "password" in cambios:
        password = cambios.pop("password")
        if password:
            usuario.hashed_password = hash_password(password)
            _invalidar_sesiones(db, usuario)
    if cambios.get("activo") is False or cambios.get("rol") not in (None, usuario.rol):
        # Cierra las sesiones abiertas del usuario
        _invalidar_sesiones(db, usuario)
    for campo, valor in cambios.items():
        if valor is not None:
            setattr(usuario, campo, valor)
    db.commit()
    return usuario


def cambiar_password(db: Session, usuario: Usuario, actual: str, nueva: str) -> Usuario:
    if not verify_password(actual, usuario.hashed_password):
        raise AuthError("La contraseña actual no es correcta.", code="invalid_credentials")
    usuario.hashed_password = hash_password(nueva)
    _invalidar_sesiones(db, usuario)
    db.commit()
    return usuario


def cerrar_sesiones(db: Session, usuario: Usuario) -> None:
    _invalidar_sesiones(db, usuario)
    db.commit()
