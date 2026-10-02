import re

from alembic import context
from sqlalchemy import create_engine

import app.models  # noqa: F401  (registra los modelos en Base.metadata)
from app.core.config import get_settings
from app.db.base import Base

target_metadata = Base.metadata

# Las particiones mensuales de recorrido_puntos (recorrido_puntos_2026_10, …_default) las crea y
# elimina el mantenimiento (app.services.recorrido); no son parte de los modelos.
_PARTICION = re.compile(r"^recorrido_puntos_(\d{4}_\d{2}|default)$")


def include_object(obj, name, type_, reflected, compare_to):
    if type_ == "table" and reflected and name and _PARTICION.match(name):
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(get_settings().database_url)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
