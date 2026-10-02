"""Comandos de administración.

    python -m app.cli crear-admin <username>
    python -m app.cli mantenimiento-gps

La contraseña se pide por consola (o se toma de ADMIN_PASSWORD en entornos
no interactivos) para que no quede en el historial del shell.
"""

import argparse
import getpass
import os
import sys

from pydantic import ValidationError
from sqlalchemy import select

from app.db.session import SessionLocal, get_engine
from app.models import RolEnum, Usuario
from app.schemas.usuarios import UsuarioCreate
from app.services import recorrido, usuarios


def crear_admin(username: str) -> int:
    password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Contraseña (mín. 8): ")
    try:
        datos = UsuarioCreate(username=username, rol=RolEnum.ADMIN, password=password)
    except ValidationError as e:
        print(f"Datos inválidos: {e}", file=sys.stderr)
        return 1

    get_engine()
    with SessionLocal() as db:
        if db.scalar(select(Usuario).where(Usuario.username == datos.username)):
            print(f"El usuario '{datos.username}' ya existe.", file=sys.stderr)
            return 1
        usuarios.crear(db, datos)
    print(f"Administrador '{datos.username}' creado.")
    return 0


def mantenimiento_gps() -> int:
    """Retención de la traza GPS: crea la partición del mes siguiente, elimina las vencidas y
    borra los puntos vencidos del mes "borde". Se programa a diario en el host (cron)."""
    get_engine()
    with SessionLocal() as db:
        resultado = recorrido.mantenimiento(db)
    print(
        f"Mantenimiento GPS: corte {resultado['corte']:%Y-%m-%d}; "
        f"particiones creadas: {resultado['particiones_creadas'] or 'ninguna'}; "
        f"eliminadas: {resultado['particiones_eliminadas'] or 'ninguna'}; "
        f"puntos borrados: {resultado['puntos_borrados']}; "
        f"cortes borrados: {resultado['eventos_borrados']}; "
        f"operaciones borradas: {resultado['operaciones_borradas']}."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="comando", required=True)
    p = sub.add_parser("crear-admin", help="Crea un usuario con rol Admin")
    p.add_argument("username")
    sub.add_parser("mantenimiento-gps", help="Aplica la retención de la traza GPS (RETENCION_GPS_DIAS)")
    args = parser.parse_args()
    if args.comando == "crear-admin":
        return crear_admin(args.username)
    if args.comando == "mantenimiento-gps":
        return mantenimiento_gps()
    return 1


if __name__ == "__main__":
    sys.exit(main())
