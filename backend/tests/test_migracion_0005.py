"""La migración 0005 (reparto) sobre una base con datos reales del esquema anterior (0004).

Crea una base temporal, la lleva a 0004, inserta datos "de antes" y migra a head con el Alembic
real, en un subproceso. Solo corre contra PostgreSQL.
"""

import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from tests.test_migracion_0004 import _alembic, base_temporal  # noqa: F401  (base_temporal es un fixture)

pytestmark = pytest.mark.skipif(
    not os.environ["DATABASE_URL"].startswith("postgresql"),
    reason="Las migraciones se prueban contra PostgreSQL",
)


def _datos_de_0004(engine):
    with engine.begin() as c:
        c.execute(text(
            "INSERT INTO usuarios (id, username, rol, hashed_password) VALUES (1, 'cajera', 'VENDEDORA', 'x')"
        ))
        c.execute(text(
            "INSERT INTO turnos (id, usuario_id, fecha_apertura, efectivo_inicial, estado) "
            "VALUES (1, 1, now(), 1000, 'ABIERTO')"
        ))
        c.execute(text(
            "INSERT INTO ventas (id, turno_id, usuario_id, fecha, metodo_pago, monto) "
            "VALUES (1, 1, 1, now(), 'EFECTIVO', 250.00)"
        ))
        c.execute(text(
            "INSERT INTO productos (id, nombre, precio_venta, stock_mostrador) VALUES (1, 'Pan', 100, 5)"
        ))


def test_los_datos_existentes_quedan_como_mostrador(base_temporal):  # noqa: F811
    _alembic(base_temporal, "upgrade", "0004")
    engine = create_engine(base_temporal)
    _datos_de_0004(engine)

    _alembic(base_temporal, "upgrade", "head")

    with engine.connect() as c:
        assert c.scalar(text("SELECT tipo::text FROM turnos WHERE id = 1")) == "MOSTRADOR"
        assert c.scalar(text("SELECT origen::text FROM ventas WHERE id = 1")) == "MOSTRADOR"
        assert c.scalar(text("SELECT punto_entrega_id FROM ventas WHERE id = 1")) is None
        assert c.scalar(text("SELECT ultimo_numero FROM numeradores WHERE tipo = 'remito'")) == 0
        assert c.scalar(text("SELECT stock_mostrador FROM productos WHERE id = 1")) == 5

        # La traza GPS está particionada por mes: mes en curso, siguiente y DEFAULT
        hijas = {n for (n,) in c.execute(text(
            "SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid "
            "JOIN pg_class p ON p.oid = i.inhparent WHERE p.relname = 'recorrido_puntos'"
        ))}
        mes = datetime.now(UTC).strftime("%Y_%m")
        assert f"recorrido_puntos_{mes}" in hijas and "recorrido_puntos_default" in hijas
        assert len(hijas) == 3
        limites = c.scalar(text(
            "SELECT pg_get_expr(relpartbound, oid) FROM pg_class WHERE relname = :n"
        ), {"n": f"recorrido_puntos_{mes}"})
        assert "+00" in limites, "los límites de la partición son UTC explícito"
    engine.dispose()


def test_el_turno_de_reparto_convive_con_el_de_mostrador_pero_no_se_duplica(base_temporal):  # noqa: F811
    _alembic(base_temporal, "upgrade", "0004")
    engine = create_engine(base_temporal)
    _datos_de_0004(engine)
    _alembic(base_temporal, "upgrade", "head")

    with engine.begin() as c:
        c.execute(text(
            "INSERT INTO usuarios (id, username, rol, hashed_password) VALUES (2, 'repa', 'REPARTIDOR', 'x')"
        ))
        c.execute(text(
            "INSERT INTO turnos (id, usuario_id, tipo, fecha_apertura, efectivo_inicial, estado) "
            "VALUES (2, 1, 'REPARTO', now(), 0, 'ABIERTO')"
        ))  # la cajera ya tenía uno de mostrador abierto: puede tener otro de reparto
    with pytest.raises(IntegrityError), engine.begin() as c:
        c.execute(text(
            "INSERT INTO turnos (id, usuario_id, tipo, fecha_apertura, efectivo_inicial, estado) "
            "VALUES (3, 1, 'REPARTO', now(), 0, 'ABIERTO')"
        ))
    engine.dispose()


def test_la_reserva_de_stock_esta_protegida_por_la_base(base_temporal):  # noqa: F811
    _alembic(base_temporal, "upgrade", "head")
    engine = create_engine(base_temporal)
    with engine.begin() as c:
        c.execute(text("INSERT INTO productos (id, nombre, precio_venta, stock_mostrador) VALUES (1, 'Pan', 100, 5)"))
        c.execute(text("UPDATE productos SET stock_reservado = 5 WHERE id = 1"))
    for sql in ("UPDATE productos SET stock_reservado = 6 WHERE id = 1",
                "UPDATE productos SET stock_reservado = -1 WHERE id = 1",
                "UPDATE productos SET stock_mostrador = 4 WHERE id = 1"):
        with pytest.raises(IntegrityError), engine.begin() as c:
            c.execute(text(sql))
    engine.dispose()


def test_la_migracion_se_deshace_y_se_repite(base_temporal):  # noqa: F811
    _alembic(base_temporal, "upgrade", "0004")
    engine = create_engine(base_temporal)
    _datos_de_0004(engine)
    _alembic(base_temporal, "upgrade", "head")
    _alembic(base_temporal, "downgrade", "0004")
    with engine.connect() as c:
        tablas = {t for (t,) in c.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))}
        assert not tablas & {"hojas_ruta", "entregas", "recorrido_puntos", "numeradores"}
        assert c.scalar(text("SELECT count(*) FROM ventas")) == 1  # los datos siguen ahí
        assert c.scalar(text("SELECT 1 FROM information_schema.columns WHERE table_name='turnos' AND column_name='tipo'")) is None
    _alembic(base_temporal, "upgrade", "head")
    _alembic(base_temporal, "check")
    with engine.connect() as c:
        assert c.scalar(text("SELECT tipo::text FROM turnos WHERE id = 1")) == "MOSTRADOR"
        assert c.scalar(text("SELECT version_num FROM alembic_version")) == "0005"
    engine.dispose()
