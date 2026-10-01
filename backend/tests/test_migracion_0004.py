"""La migración 0004 sobre una base con datos reales del esquema anterior (0002).

Crea una base temporal, la lleva a 0002, inserta ventas "de antes" y migra a head con el
Alembic real, en un subproceso. Solo corre contra PostgreSQL.
"""

import os
import subprocess
import sys
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BACKEND = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(
    not os.environ["DATABASE_URL"].startswith("postgresql"),
    reason="Las migraciones se prueban contra PostgreSQL",
)


@pytest.fixture
def base_temporal():
    # conftest deja la URL como "postgresql://": usamos el driver psycopg 3, igual que la app
    admin_url = make_url(os.environ["DATABASE_URL"]).set(drivername="postgresql+psycopg", database="postgres")
    nombre = f"erp_mig_{uuid.uuid4().hex[:8]}"
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{nombre}"'))
    url = admin_url.set(database=nombre)
    yield url
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{nombre}" WITH (FORCE)'))
    admin.dispose()


def _alembic(url, *args):
    env = {**os.environ, "DATABASE_URL": url.render_as_string(hide_password=False)}
    r = subprocess.run(
        [sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env, capture_output=True, text=True
    )
    assert r.returncode == 0, r.stderr[-2000:]


def _ventas_viejas(engine):
    """Datos como los dejaba la versión anterior: sin ventas_pagos."""
    with engine.begin() as c:
        c.execute(text(
            "INSERT INTO usuarios (id, username, rol, hashed_password) VALUES (1, 'cajera', 'VENDEDORA', 'x')"
        ))
        c.execute(text(
            "INSERT INTO turnos (id, usuario_id, fecha_apertura, efectivo_inicial, estado) "
            "VALUES (1, 1, now(), 1000, 'CERRADO')"
        ))
        for venta_id, metodo, monto in [
            (1, "EFECTIVO", "7500.00"), (2, "EFECTIVO", "25900.50"), (3, "TRANSFERENCIA", "16700.00"),
            (4, "TARJETA", "5400.00"), (5, "EFECTIVO", "0.01"),
        ]:
            c.execute(text(
                "INSERT INTO ventas (id, turno_id, usuario_id, fecha, metodo_pago, monto) "
                "VALUES (:i, 1, 1, now(), :m, :monto)"
            ), {"i": venta_id, "m": metodo, "monto": monto})
        c.execute(text(
            "INSERT INTO productos (id, nombre, precio_venta, stock_mostrador) VALUES (1, 'Pan', 100, 5)"
        ))


def test_backfill_crea_un_pago_por_cada_venta_existente(base_temporal):
    _alembic(base_temporal, "upgrade", "0002")
    engine = create_engine(base_temporal)
    _ventas_viejas(engine)

    _alembic(base_temporal, "upgrade", "head")

    with engine.connect() as c:
        filas = c.execute(text(
            "SELECT v.id, v.monto, v.metodo_pago::text, p.metodo_pago::text, p.monto, p.estado::text, p.fecha = v.fecha "
            "FROM ventas v LEFT JOIN ventas_pagos p ON p.venta_id = v.id ORDER BY v.id"
        )).all()
        assert len(filas) == 5, "cada venta tiene exactamente un pago"
        for _vid, monto, metodo, pago_metodo, pago_monto, estado, misma_fecha in filas:
            assert pago_monto == monto, "el pago es por el total de la venta"
            assert pago_metodo == metodo, "conserva el medio original"
            assert estado == "APROBADO" and misma_fecha
        total_ventas, total_pagos = c.execute(
            text("SELECT (SELECT sum(monto) FROM ventas), (SELECT sum(monto) FROM ventas_pagos)")
        ).one()
        assert total_ventas == total_pagos == Decimal("55500.51")
        # Lo demás quedó con valores neutros
        assert c.scalar(text("SELECT stock_reservado FROM productos WHERE id = 1")) == 0
        assert c.scalar(text("SELECT count(*) FROM arqueos WHERE cobros_efectivo IS NOT NULL")) == 0
    engine.dispose()


def test_la_migracion_es_reversible_y_repetible(base_temporal):
    _alembic(base_temporal, "upgrade", "0002")
    engine = create_engine(base_temporal)
    _ventas_viejas(engine)
    _alembic(base_temporal, "upgrade", "head")
    _alembic(base_temporal, "downgrade", "0002")
    with engine.connect() as c:
        tablas = {t for (t,) in c.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))}
        assert not tablas & {"ventas_pagos", "puntos_entrega", "movimientos_cuenta_corriente"}
        assert c.scalar(text("SELECT count(*) FROM ventas")) == 5  # los datos viejos siguen ahí
    _alembic(base_temporal, "upgrade", "head")
    with engine.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM ventas_pagos")) == 5
    engine.dispose()


def test_los_modelos_coinciden_con_las_migraciones(base_temporal):
    _alembic(base_temporal, "upgrade", "head")
    _alembic(base_temporal, "check")


def test_stock_negativo_frena_la_migracion_con_un_mensaje_claro(base_temporal):
    _alembic(base_temporal, "upgrade", "0002")
    engine = create_engine(base_temporal)
    with engine.begin() as c:
        c.execute(text("INSERT INTO productos (id, nombre, precio_venta, stock_mostrador) VALUES (1, 'Roto', 10, -3)"))
    env = {**os.environ, "DATABASE_URL": base_temporal.render_as_string(hide_password=False)}
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env,
                       capture_output=True, text=True)
    assert r.returncode != 0 and "stock_mostrador negativo" in r.stderr
    with engine.connect() as c:  # y no quedó a medio migrar
        assert c.scalar(text("SELECT to_regclass('public.ventas_pagos')")) is None
        assert c.scalar(text("SELECT version_num FROM alembic_version")) == "0002"
    engine.dispose()
