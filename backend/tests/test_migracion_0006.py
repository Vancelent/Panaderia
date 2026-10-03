"""La migración 0006 (autenticación híbrida) sobre una base con datos del esquema anterior (0005).
Solo corre contra PostgreSQL."""

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from tests.test_migracion_0004 import _alembic, base_temporal  # noqa: F401  (base_temporal es un fixture)

pytestmark = pytest.mark.skipif(
    not os.environ["DATABASE_URL"].startswith("postgresql"),
    reason="Las migraciones se prueban contra PostgreSQL",
)


def _usuarios(engine):
    with engine.begin() as c:
        c.execute(text(
            "INSERT INTO usuarios (id, username, rol, hashed_password) VALUES "
            "(1, 'jefe', 'ADMIN', 'x'), (2, 'cajera', 'VENDEDORA', 'x')"
        ))


def test_los_usuarios_existentes_quedan_sin_correo_ni_pin(base_temporal):  # noqa: F811
    _alembic(base_temporal, "upgrade", "0005")
    engine = create_engine(base_temporal)
    _usuarios(engine)
    _alembic(base_temporal, "upgrade", "head")
    with engine.connect() as c:
        filas = c.execute(text("SELECT username, email, pin_hash, pin_fallidos, pin_bloqueado FROM usuarios ORDER BY id")).all()
        assert filas == [("jefe", None, None, 0, False), ("cajera", None, None, 0, False)]
        tablas = {t for (t,) in c.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))}
        assert {"identidades_externas", "terminales", "dispositivos", "refresh_tokens"} <= tablas
    engine.dispose()


def test_el_correo_es_unico_y_la_identidad_de_google_tambien(base_temporal):  # noqa: F811
    _alembic(base_temporal, "upgrade", "head")
    engine = create_engine(base_temporal)
    _usuarios(engine)
    with engine.begin() as c:
        c.execute(text("UPDATE usuarios SET email = 'ana@gmail.com' WHERE id = 1"))
        c.execute(text("INSERT INTO identidades_externas (usuario_id, proveedor, sub, email, creado_en) "
                       "VALUES (1, 'GOOGLE', 'sub-1', 'ana@gmail.com', now())"))
    for sql in ("UPDATE usuarios SET email = 'ana@gmail.com' WHERE id = 2",
                "INSERT INTO identidades_externas (usuario_id, proveedor, sub, email, creado_en) "
                "VALUES (2, 'GOOGLE', 'sub-1', 'otro@gmail.com', now())",
                "INSERT INTO terminales (nombre, tipo, secreto_hash, creado_por_id, creado_en) "
                "VALUES ('A', 'CAJA', 'h', 1, now()), ('B', 'CAJA', 'h', 1, now())"):
        with pytest.raises(IntegrityError), engine.begin() as c:
            c.execute(text(sql))
    engine.dispose()


def test_la_migracion_se_deshace_y_se_repite(base_temporal):  # noqa: F811
    _alembic(base_temporal, "upgrade", "0005")
    engine = create_engine(base_temporal)
    _usuarios(engine)
    _alembic(base_temporal, "upgrade", "head")
    _alembic(base_temporal, "downgrade", "0005")
    with engine.connect() as c:
        tablas = {t for (t,) in c.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))}
        assert not tablas & {"identidades_externas", "terminales", "dispositivos", "refresh_tokens"}
        assert c.scalar(text("SELECT count(*) FROM usuarios")) == 2  # los datos siguen
        assert c.scalar(text("SELECT count(*) FROM information_schema.columns WHERE table_name = 'usuarios' "
                             "AND column_name IN ('email', 'pin_hash', 'pin_fallidos', 'pin_bloqueado')")) == 0
        assert c.scalar(text("SELECT count(*) FROM pg_type WHERE typname IN ('proveedoridentidadenum', 'tipoterminalenum')")) == 0
    _alembic(base_temporal, "upgrade", "head")
    _alembic(base_temporal, "check")  # los modelos coinciden con las migraciones
    engine.dispose()
