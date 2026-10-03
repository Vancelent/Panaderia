"""Autenticación híbrida: Google, PIN en terminales registrados y sesiones de la app móvil (Fase 4).

- usuarios: email (único, minúsculas), pin_hash, pin_fallidos, pin_bloqueado
- identidades_externas: cuenta de Google vinculada a un usuario (UNIQUE proveedor + sub)
- terminales: equipos donde se puede entrar con PIN (solo se guarda el hash del secreto)
- dispositivos y refresh_tokens: sesiones de la app móvil (refresh opaco, rotativo)

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-02
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)

NUEVOS_ENUMS = {
    "proveedoridentidadenum": ("GOOGLE",),
    "tipoterminalenum": ("CAJA", "CUADRA"),
}


def _enum(nombre: str) -> postgresql.ENUM:
    """Referencia a un tipo ya creado (create_type=False)."""
    return postgresql.ENUM(*NUEVOS_ENUMS[nombre], name=nombre, create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    for nombre, valores in NUEVOS_ENUMS.items():
        postgresql.ENUM(*valores, name=nombre).create(bind, checkfirst=True)

    op.add_column("usuarios", sa.Column("email", sa.String(120)))
    op.add_column("usuarios", sa.Column("pin_hash", sa.String(255)))
    op.add_column("usuarios", sa.Column("pin_fallidos", sa.Integer, nullable=False, server_default="0"))
    op.add_column("usuarios", sa.Column("pin_bloqueado", sa.Boolean, nullable=False, server_default="false"))
    op.create_unique_constraint("uq_usuarios_email", "usuarios", ["email"])

    op.create_table(
        "identidades_externas",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("usuario_id", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=False, index=True),
        sa.Column("proveedor", _enum("proveedoridentidadenum"), nullable=False),
        sa.Column("sub", sa.String(255), nullable=False),
        sa.Column("email", sa.String(120), nullable=False),
        sa.Column("creado_en", TS, nullable=False),
        sa.Column("ultimo_uso", TS),
        sa.UniqueConstraint("proveedor", "sub"),
    )

    op.create_table(
        "terminales",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("nombre", sa.String(80), nullable=False),
        sa.Column("tipo", _enum("tipoterminalenum"), nullable=False),
        sa.Column("secreto_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("activo", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("creado_por_id", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("creado_en", TS, nullable=False),
        sa.Column("ultimo_uso", TS),
    )

    op.create_table(
        "dispositivos",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("usuario_id", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=False, index=True),
        sa.Column("nombre", sa.String(80), nullable=False),
        sa.Column("plataforma", sa.String(20), nullable=False),
        sa.Column("creado_en", TS, nullable=False),
        sa.Column("ultimo_uso", TS),
        sa.Column("revocado_en", TS),
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("dispositivo_id", sa.Integer, sa.ForeignKey("dispositivos.id"), nullable=False, index=True),
        sa.Column("familia_id", sa.Uuid, nullable=False, index=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("emitido_en", TS, nullable=False),
        sa.Column("expira_en", TS, nullable=False),
        sa.Column("usado_en", TS),
        sa.Column("reemplazado_por_id", sa.Integer, sa.ForeignKey("refresh_tokens.id")),
        sa.Column("revocado_en", TS),
        sa.Column("metodo", sa.String(10), nullable=False),
        sa.Column("auth_time", TS, nullable=False),
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_table("refresh_tokens")
    op.drop_table("dispositivos")
    op.drop_table("terminales")
    op.drop_table("identidades_externas")
    op.drop_constraint("uq_usuarios_email", "usuarios", type_="unique")
    op.drop_column("usuarios", "pin_bloqueado")
    op.drop_column("usuarios", "pin_fallidos")
    op.drop_column("usuarios", "pin_hash")
    op.drop_column("usuarios", "email")
    for nombre, valores in reversed(list(NUEVOS_ENUMS.items())):
        postgresql.ENUM(*valores, name=nombre).drop(bind, checkfirst=True)
