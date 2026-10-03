"""Terminales registrados y login con PIN (docs/rfc-001 §2.3).

El PIN es cómodo (cambio de cajera en segundos) pero débil por sí solo: de 4 a 6 dígitos. Por eso solo
funciona en un **equipo registrado**, cuyo secreto vive en una cookie httpOnly y del que el servidor
guarda únicamente el hash. El PIN, además, se guarda con bcrypt sobre un HMAC con un secreto del
servidor (`PIN_PEPPER`).
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AuthError, ConflictError, NotFoundError, UnprocessableError
from app.core.security import (
    hash_pin,
    hash_token_opaco,
    nuevo_token_opaco,
    verify_pin,
    verify_pin_dummy,
)
from app.models import RolEnum, Terminal, TipoTerminalEnum, Usuario

# Quién puede usar PIN en cada tipo de equipo (docs/rfc-001 §2.1)
ROLES_POR_TERMINAL: dict[TipoTerminalEnum, tuple[RolEnum, ...]] = {
    TipoTerminalEnum.CAJA: (RolEnum.ENCARGADA, RolEnum.VENDEDORA),
    TipoTerminalEnum.CUADRA: (RolEnum.PANADERO,),
}
ROLES_CON_PIN = tuple({r for roles in ROLES_POR_TERMINAL.values() for r in roles})


def ahora() -> datetime:
    return datetime.now(UTC)


# ---------- Terminales ----------


def registrar(db: Session, actor: Usuario, nombre: str, tipo: TipoTerminalEnum) -> tuple[Terminal, str]:
    """Da de alta el equipo. Devuelve también el secreto en claro, que solo existe en esta respuesta
    (viaja en la cookie del equipo); la base guarda su hash."""
    secreto = nuevo_token_opaco()
    terminal = Terminal(
        nombre=nombre, tipo=tipo, secreto_hash=hash_token_opaco(secreto), creado_por_id=actor.id
    )
    db.add(terminal)
    db.commit()
    return terminal, secreto


def desde_secreto(db: Session, secreto: str | None) -> Terminal | None:
    """El terminal activo al que pertenece el secreto de la cookie, si existe."""
    if not secreto:
        return None
    return db.scalar(
        select(Terminal).where(Terminal.secreto_hash == hash_token_opaco(secreto), Terminal.activo.is_(True))
    )


def listar(db: Session) -> list[Terminal]:
    return list(db.scalars(select(Terminal).order_by(Terminal.id)))


def actualizar(db: Session, terminal_id: int, nombre: str | None, activo: bool | None) -> Terminal:
    """Desactivar un equipo invalida las sesiones PIN emitidas en él (lo verifica `get_current_user`)."""
    terminal = db.get(Terminal, terminal_id)
    if terminal is None:
        raise NotFoundError("Terminal no encontrado.")
    if nombre is not None:
        terminal.nombre = nombre
    if activo is not None:
        terminal.activo = activo
    db.commit()
    return terminal


def usuarios_con_pin(db: Session, terminal: Terminal) -> list[Usuario]:
    return list(
        db.scalars(
            select(Usuario)
            .where(
                Usuario.activo.is_(True),
                Usuario.pin_hash.is_not(None),
                Usuario.rol.in_(ROLES_POR_TERMINAL[terminal.tipo]),
            )
            .order_by(Usuario.nombre, Usuario.username)
        )
    )


# ---------- Login con PIN ----------


def _credenciales_invalidas() -> AuthError:
    return AuthError("Usuario o PIN incorrectos.", code="invalid_credentials")


def iniciar_sesion_pin(db: Session, terminal: Terminal, usuario_id: int, pin: str) -> Usuario:
    """Verifica el PIN. Los fallos se cuentan en la base y a los 5 seguidos el PIN queda bloqueado
    (se libera con Google, contraseña o un admin)."""
    settings = get_settings()
    # El bloqueo de la fila serializa los intentos simultáneos: no se pueden probar más PIN en paralelo
    usuario = db.scalar(select(Usuario).where(Usuario.id == usuario_id).with_for_update())
    permitido = (
        usuario is not None
        and usuario.activo
        and usuario.pin_hash is not None
        and usuario.rol in ROLES_POR_TERMINAL[terminal.tipo]
    )
    if not permitido:
        verify_pin_dummy(pin)
        db.rollback()
        raise _credenciales_invalidas()
    if usuario.pin_bloqueado:
        db.rollback()
        raise AuthError(
            "El PIN está bloqueado por intentos fallidos. Ingresá con Google o contraseña, o pedile "
            "a un administrador que lo desbloquee.",
            code="pin_bloqueado",
        )
    if not verify_pin(pin, usuario.pin_hash):
        usuario.pin_fallidos += 1
        if usuario.pin_fallidos >= settings.pin_max_fallos:
            usuario.pin_bloqueado = True
        db.commit()  # el fallo tiene que quedar registrado aunque se rechace el pedido
        raise _credenciales_invalidas()
    usuario.pin_fallidos = 0
    terminal.ultimo_uso = ahora()
    db.commit()
    return usuario


# ---------- Administración de PIN ----------


def _es_pin_debil(pin: str) -> bool:
    secuencia = "0123456789012345678901234567890"
    return len(set(pin)) == 1 or pin in secuencia or pin in secuencia[::-1]


def establecer_pin(db: Session, usuario: Usuario, pin: str) -> Usuario:
    if usuario.rol not in ROLES_CON_PIN:
        raise ConflictError(
            "Solo la encargada, la vendedora y el panadero pueden usar PIN.", code="rol_sin_pin"
        )
    if _es_pin_debil(pin):
        raise UnprocessableError(
            "Ese PIN es demasiado fácil de adivinar (dígitos repetidos o en secuencia).", code="pin_debil"
        )
    usuario.pin_hash = hash_pin(pin)
    usuario.pin_fallidos = 0
    usuario.pin_bloqueado = False
    usuario.token_version += 1  # cierra las sesiones abiertas con el PIN anterior
    db.commit()
    return usuario


def quitar_pin(db: Session, usuario: Usuario) -> Usuario:
    usuario.pin_hash = None
    usuario.pin_fallidos = 0
    usuario.pin_bloqueado = False
    usuario.token_version += 1
    db.commit()
    return usuario


def desbloquear_pin(usuario: Usuario) -> None:
    """Sin commit: lo llaman los logins con contraseña o Google, que ya confirman al final."""
    usuario.pin_fallidos = 0
    usuario.pin_bloqueado = False
