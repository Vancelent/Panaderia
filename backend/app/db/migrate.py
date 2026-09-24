"""Aplica las migraciones al arrancar.

Si la base viene del esquema v1 (creado con create_all, sin tabla
alembic_version) primero la marca como revisión 0001 para que Alembic
aplique solo los cambios nuevos sin perder datos.

    python -m app.db.migrate
"""

import logging
import time
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.exc import OperationalError

from app.db.session import get_engine

log = logging.getLogger("migrate")
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def _esperar_bd(intentos: int = 30, espera: float = 1.0):
    engine = get_engine()
    for i in range(1, intentos + 1):
        try:
            with engine.connect():
                return engine
        except OperationalError:
            log.info("Base de datos no disponible (%s/%s), reintentando...", i, intentos)
            time.sleep(espera)
    raise RuntimeError("No se pudo conectar a la base de datos.")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    engine = _esperar_bd()
    cfg = Config(str(ALEMBIC_INI))
    tablas = set(inspect(engine).get_table_names())
    if "usuarios" in tablas and "alembic_version" not in tablas:
        log.info("Esquema v1 detectado: marcando como revisión 0001.")
        command.stamp(cfg, "0001")
    command.upgrade(cfg, "head")
    log.info("Migraciones al día.")


if __name__ == "__main__":
    main()
