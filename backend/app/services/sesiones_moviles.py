"""Sesiones de la app móvil: access token corto + refresh opaco rotativo (docs/rfc-001 §8.3).

- **Access token:** JWT de 15 minutos con `aud="movil"` y `dsp=<dispositivo>`. Solo vive en memoria.
- **Refresh token:** 256 bits aleatorios; en la base solo su SHA-256. Cada uso emite un par nuevo.
- **Reutilización:** usar un refresh ya usado **fuera de la ventana de gracia** (30 s) revoca toda la
  familia: alguien más tiene una copia. Dentro de la ventana se tolera, porque con señal intermitente la
  respuesta de la rotación puede perderse y la app reintenta con el token viejo.
- **Reautenticación:** el refresh no renueva `auth_time`; la gestión sensible vuelve a pedir contraseña
  o Google.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AuthError, NotFoundError
from app.core.security import (
    AUD_MOVIL,
    create_access_token,
    hash_token_opaco,
    nuevo_token_opaco,
)
from app.models import Dispositivo, RefreshToken, Usuario
from app.schemas.auth import DispositivoIn


def ahora() -> datetime:
    return datetime.now(UTC)


def _aware(dt: datetime) -> datetime:
    """SQLite devuelve fechas sin zona horaria; PostgreSQL, con ella."""
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _sesion_invalida() -> AuthError:
    return AuthError("Sesión inválida o expirada.", code="refresh_invalido")


def emitir_access(
    usuario: Usuario, dispositivo: Dispositivo, *, amr: str, auth_time: datetime
) -> tuple[str, int]:
    minutos = get_settings().movil_access_minutos
    token = create_access_token(
        user_id=usuario.id, token_version=usuario.token_version, amr=amr, auth_time=auth_time,
        audience=AUD_MOVIL, dispositivo_id=dispositivo.id, minutos=minutos,
    )
    return token, minutos * 60


def _nuevo_refresh(
    db: Session, dispositivo: Dispositivo, familia: uuid.UUID, metodo: str, auth_time: datetime
) -> tuple[RefreshToken, str]:
    plano = nuevo_token_opaco()
    rt = RefreshToken(
        dispositivo_id=dispositivo.id, familia_id=familia, token_hash=hash_token_opaco(plano),
        expira_en=ahora() + timedelta(days=get_settings().movil_refresh_dias),
        metodo=metodo, auth_time=auth_time,
    )
    db.add(rt)
    db.flush()
    return rt, plano


def abrir_sesion(
    db: Session, usuario: Usuario, datos: DispositivoIn, *, amr: str
) -> tuple[Dispositivo, str, str, int]:
    """Registra el celular y emite el primer par de tokens: (dispositivo, access, refresh, segundos)."""
    dispositivo = Dispositivo(
        usuario_id=usuario.id, nombre=datos.nombre, plataforma=datos.plataforma, ultimo_uso=ahora()
    )
    db.add(dispositivo)
    db.flush()
    auth_time = ahora()
    _, refresh = _nuevo_refresh(db, dispositivo, uuid.uuid4(), amr, auth_time)
    access, segundos = emitir_access(usuario, dispositivo, amr=amr, auth_time=auth_time)
    db.commit()
    return dispositivo, access, refresh, segundos


def rotar(db: Session, refresh_plano: str) -> tuple[Usuario, Dispositivo, str, str, int]:
    """Canjea un refresh por un par nuevo. Devuelve (usuario, dispositivo, access, refresh, segundos)."""
    s = get_settings()
    rt = db.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_token_opaco(refresh_plano))
        .with_for_update()
    )
    if rt is None:
        raise _sesion_invalida()
    dispositivo = rt.dispositivo
    usuario = db.get(Usuario, dispositivo.usuario_id)
    if dispositivo.revocado_en is not None or rt.revocado_en is not None:
        raise _sesion_invalida()
    if usuario is None or not usuario.activo:
        raise _sesion_invalida()
    t = ahora()
    if _aware(rt.expira_en) <= t:
        raise _sesion_invalida()

    if rt.usado_en is not None:
        if (t - _aware(rt.usado_en)).total_seconds() > s.movil_refresh_gracia_segundos:
            # Reutilización: la familia entera queda revocada y la persona tiene que volver a ingresar
            db.execute(
                update(RefreshToken)
                .where(RefreshToken.familia_id == rt.familia_id, RefreshToken.revocado_en.is_(None))
                .values(revocado_en=t)
            )
            db.commit()
            raise AuthError(
                "Se detectó un uso indebido de la sesión. Volvé a ingresar.", code="refresh_reutilizado"
            )
        # Dentro de la ventana de gracia: reintento tras una respuesta perdida. `usado_en` conserva el
        # primer uso, así la tolerancia no se prolonga con cada reintento.
    else:
        rt.usado_en = t

    auth_time = _aware(rt.auth_time)
    nuevo, plano = _nuevo_refresh(db, dispositivo, rt.familia_id, rt.metodo, auth_time)
    rt.reemplazado_por_id = nuevo.id
    dispositivo.ultimo_uso = t
    access, segundos = emitir_access(usuario, dispositivo, amr=rt.metodo, auth_time=auth_time)
    db.commit()
    return usuario, dispositivo, access, plano, segundos


def cerrar(db: Session, refresh_plano: str) -> None:
    """Cierra la sesión del celular (revoca el dispositivo). Es idempotente."""
    rt = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token_opaco(refresh_plano)))
    if rt is not None:
        revocar(db, rt.dispositivo_id)


def revocar(db: Session, dispositivo_id: int, usuario_id: int | None = None) -> Dispositivo:
    """Revoca un celular: sus access tokens dejan de valer en el acto y sus refresh, también."""
    dispositivo = db.get(Dispositivo, dispositivo_id)
    if dispositivo is None or (usuario_id is not None and dispositivo.usuario_id != usuario_id):
        raise NotFoundError("Dispositivo no encontrado.")
    t = ahora()
    if dispositivo.revocado_en is None:
        dispositivo.revocado_en = t
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.dispositivo_id == dispositivo.id, RefreshToken.revocado_en.is_(None))
        .values(revocado_en=t)
    )
    db.commit()
    return dispositivo


def dispositivo_activo(db: Session, dispositivo_id: int, usuario_id: int) -> Dispositivo:
    dispositivo = db.get(Dispositivo, dispositivo_id)
    if dispositivo is None or dispositivo.usuario_id != usuario_id or dispositivo.revocado_en is not None:
        raise NotFoundError("Dispositivo no encontrado.")
    return dispositivo


def revocar_todos(db: Session, usuario_id: int) -> None:
    """Revoca todos los celulares y refresh del usuario (sin commit: lo hace quien llama).

    Va junto con subir `token_version`: eso corta los access tokens, y esto evita que un refresh
    robado los vuelva a emitir después de "cerrar todas las sesiones" o de cambiar la contraseña.
    """
    t = ahora()
    ids = select(Dispositivo.id).where(Dispositivo.usuario_id == usuario_id)
    db.execute(
        update(Dispositivo)
        .where(Dispositivo.usuario_id == usuario_id, Dispositivo.revocado_en.is_(None))
        .values(revocado_en=t)
    )
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.dispositivo_id.in_(ids), RefreshToken.revocado_en.is_(None))
        .values(revocado_en=t)
    )


def listar(db: Session, usuario_id: int) -> list[Dispositivo]:
    return list(
        db.scalars(
            select(Dispositivo).where(Dispositivo.usuario_id == usuario_id).order_by(Dispositivo.id.desc())
        )
    )
