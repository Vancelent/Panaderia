"""Concurrencia de la autenticación contra PostgreSQL (el bloqueo de filas no existe en SQLite)."""

import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select

from app.api.v1.auth import get_pin_limiter
from app.db.session import SessionLocal
from app.models import RefreshToken, RolEnum, Usuario
from tests.conftest import login
from tests.test_auth_hibrida import _con_pin, _kiosko, _pin, _registrar_terminal
from tests.test_auth_movil import _entrar, _renovar, crear_usuario

pytestmark = pytest.mark.skipif(
    not os.environ["DATABASE_URL"].startswith("postgresql"),
    reason="El bloqueo de filas (FOR UPDATE) solo se puede probar en Postgres",
)


def test_probar_pin_en_paralelo_no_da_mas_intentos_que_el_limite(como):
    """Veinte intentos simultáneos con PIN incorrecto: se cuentan exactamente 5 y después se bloquea.
    Sin el bloqueo de la fila, los intentos que corren a la vez leerían el mismo contador."""
    como(RolEnum.ADMIN, "jefe")
    secreto = _registrar_terminal(login("jefe"))
    vend = _con_pin("vendedora", RolEnum.VENDEDORA)
    equipos = [_kiosko(secreto) for _ in range(20)]

    with ThreadPoolExecutor(max_workers=10) as pool:
        respuestas = list(pool.map(lambda c: _pin(c, vend.id, "1357"), equipos))
    codigos = [r.json()["error"]["code"] for r in respuestas if r.status_code == 401]
    assert codigos.count("invalid_credentials") == 5
    assert codigos.count("pin_bloqueado") == len(codigos) - 5
    with SessionLocal() as s:
        u = s.get(Usuario, vend.id)
        assert (u.pin_fallidos, u.pin_bloqueado) == (5, True)
    get_pin_limiter.cache_clear()  # el límite por equipo ya frenó parte de los intentos
    assert _pin(_kiosko(secreto), vend.id, "2580").json()["error"]["code"] == "pin_bloqueado"


def test_rotaciones_simultaneas_del_mismo_refresh_no_se_pisan():
    """La app reintenta con el mismo refresh mientras la primera respuesta sigue en camino: las dos
    rotaciones se serializan y, dentro de la ventana de gracia, las dos tienen éxito."""
    crear_usuario("repa", RolEnum.REPARTIDOR)
    s = _entrar().json()
    with ThreadPoolExecutor(max_workers=6) as pool:
        respuestas = list(pool.map(lambda _: _renovar(s["refresh_token"]), range(6)))
    assert [r.status_code for r in respuestas] == [200] * 6, [r.text for r in respuestas]
    nuevos = {r.json()["refresh_token"] for r in respuestas}
    assert len(nuevos) == 6 and s["refresh_token"] not in nuevos
    with SessionLocal() as db:
        # Seis hijos + el original, todos de la misma familia y ninguno revocado
        tokens = db.scalars(select(RefreshToken)).all()
        assert len(tokens) == 7 and len({t.familia_id for t in tokens}) == 1
        assert all(t.revocado_en is None for t in tokens)
        assert db.scalar(select(func.count()).select_from(RefreshToken).where(RefreshToken.usado_en.is_not(None))) == 1
