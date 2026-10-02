"""Piezas de la infraestructura de producción: prefijo __Host-, pool de conexiones y verificaciones."""

import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.db.session import SessionLocal
from app.models import Cliente, Producto, RolEnum
from app.services import contabilidad, stock
from tests.conftest import PASSWORD, crear_usuario
from tests.conftest import Cliente as ClienteHttp
from tests.test_entregas import _confirmar, _hoja

BACKEND = Path(__file__).resolve().parents[1]
BASE = {"database_url": "sqlite:///x.db", "jwt_secret": "x" * 40}


# ---------- Cookies __Host- ----------


def test_el_prefijo_host_se_antepone_a_las_cookies_de_sesion_y_csrf():
    s = Settings(**BASE, cookie_prefix="__Host-", cookie_secure=True)
    assert s.cookie_name == "__Host-panaderia_session"
    assert s.csrf_cookie_name == "__Host-panaderia_csrf"
    # Sin prefijo, los nombres de siempre
    s = Settings(**BASE)
    assert (s.cookie_name, s.csrf_cookie_name) == ("panaderia_session", "panaderia_csrf")


def test_el_prefijo_host_exige_cookies_secure_y_solo_acepta_valores_conocidos():
    with pytest.raises(ValidationError, match="COOKIE_SECURE"):
        Settings(**BASE, cookie_prefix="__Host-", cookie_secure=False)
    with pytest.raises(ValidationError):
        Settings(**BASE, cookie_prefix="__Secure-")


def test_con_prefijo_host_la_sesion_funciona_y_el_logout_la_borra(monkeypatch):
    """Una cookie __Host- se rechaza si no es Secure, Path=/ y sin Domain: tanto al crearla como
    al borrarla. Se prueba con el cliente HTTP real de la app."""
    from app.core import config

    crear_usuario("cajera", RolEnum.VENDEDORA)
    monkeypatch.setenv("COOKIE_PREFIX", "__Host-")
    monkeypatch.setenv("COOKIE_SECURE", "true")
    config.get_settings.cache_clear()
    try:
        from app.main import app

        c = ClienteHttp(app, base_url="https://testserver")
        r = c.post("/api/v1/auth/login", json={"username": "cajera", "password": PASSWORD})
        assert r.status_code == 200, r.text
        cookies = r.headers.get_list("set-cookie")
        assert len(cookies) == 2
        for cookie in cookies:
            assert cookie.startswith("__Host-panaderia_")
            assert "Secure" in cookie and "Path=/" in cookie and "Domain" not in cookie
            assert "SameSite=strict" in cookie
        csrf = c.cookies.get("__Host-panaderia_csrf")
        assert csrf
        assert c.get("/api/v1/auth/me").status_code == 200
        borradas = c.post(
            "/api/v1/auth/logout", headers={"X-CSRF-Token": csrf}
        ).headers.get_list("set-cookie")
        assert len(borradas) == 2
        for cookie in borradas:
            assert cookie.startswith("__Host-panaderia_")
            assert "Secure" in cookie and "Max-Age=0" in cookie and "Path=/" in cookie
    finally:
        monkeypatch.undo()
        config.get_settings.cache_clear()


# ---------- Pool de conexiones ----------


def test_el_pool_se_configura_por_variables_de_entorno():
    s = Settings(**BASE, db_pool_size=4, db_max_overflow=2)
    assert (s.db_pool_size, s.db_max_overflow) == (4, 2)
    s = Settings(**BASE)
    assert (s.db_pool_size, s.db_max_overflow) == (5, 10)
    with pytest.raises(ValidationError):
        Settings(**BASE, db_pool_size=0)


@pytest.mark.skipif(not os.environ["DATABASE_URL"].startswith("postgresql"), reason="SQLite no usa pool")
def test_el_engine_de_postgres_usa_el_pool_configurado(monkeypatch):
    from app.core import config
    from app.db import session

    original = session._engine
    monkeypatch.setenv("DB_POOL_SIZE", "4")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "2")
    config.get_settings.cache_clear()
    session._engine = None
    try:
        engine = session.get_engine()
        assert (engine.pool.size(), engine.pool._max_overflow) == (4, 2)
        engine.dispose()
    finally:
        monkeypatch.undo()
        config.get_settings.cache_clear()
        session._engine = original
        session.SessionLocal.configure(bind=original)


# ---------- Verificaciones del cron ----------


def _cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "app.cli", *args], cwd=BACKEND, env={**os.environ},
        capture_output=True, text=True,
    )


def test_verificar_reservas_detecta_diferencias(reparto):
    r, pan = reparto, reparto["pan"]
    with SessionLocal() as s:
        assert stock.verificar_reservas(s) == []
    hoja = _hoja(r, (r["centro"], {pan: 8}))
    assert _confirmar(r, hoja["id"]).status_code == 200
    with SessionLocal() as s:
        assert stock.verificar_reservas(s) == []  # 8 reservados = lo que reserva la hoja confirmada
        s.get(Producto, pan).stock_reservado = 3  # alguien tocó la base a mano
        s.commit()
        assert stock.verificar_reservas(s) == [
            {"producto_id": pan, "nombre": "Pan", "reservado": 3, "esperado": 8}
        ]


def test_verificar_saldos_detecta_diferencias(reparto):
    cliente_id = reparto["cliente"]["id"]
    with SessionLocal() as s:
        assert contabilidad.verificar_saldos(s) == []
        s.get(Cliente, cliente_id).saldo_cuenta_corriente = Decimal("999")  # sin movimiento que lo respalde
        s.commit()
        diferencias = contabilidad.verificar_saldos(s)
        assert [(d["cliente_id"], d["saldo"], d["calculado"]) for d in diferencias] == [
            (cliente_id, Decimal("999"), Decimal("0"))
        ]


def test_los_comandos_de_verificacion_salen_con_codigo_1_si_hay_diferencias(reparto):
    """Lo que mira el cron: código 0 = consistente, 1 = hay que revisar."""
    pan = reparto["pan"]
    assert _cli("verificar-reservas").returncode == 0
    assert _cli("verificar-saldos").returncode == 0
    with SessionLocal() as s:
        s.get(Producto, pan).stock_reservado = 2
        s.get(Cliente, reparto["cliente"]["id"]).saldo_cuenta_corriente = Decimal("50")
        s.commit()
    r = _cli("verificar-reservas")
    assert r.returncode == 1 and "DIFERENCIA producto" in r.stderr and "reservado 2, esperado 0" in r.stderr
    r = _cli("verificar-saldos")
    assert r.returncode == 1 and "DIFERENCIA cliente" in r.stderr
    assert "verificar-saldos" in _cli("--help").stdout
