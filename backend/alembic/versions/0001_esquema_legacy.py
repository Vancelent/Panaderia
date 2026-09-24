"""Esquema original (v1) tal como lo creaba Base.metadata.create_all.

Las bases existentes ya tienen este esquema: el entrypoint las marca con
`alembic stamp 0001` antes de aplicar las migraciones siguientes.

Revision ID: 0001
Revises:
Create Date: 2026-09-24
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

rolenum = sa.Enum("ADMIN", "ENCARGADA", "VENDEDORA", "PANADERO", name="rolenum")
estadoturnoenum = sa.Enum("ABIERTO", "CERRADO", name="estadoturnoenum")


def _id():
    return sa.Column("id", sa.Integer, primary_key=True, index=True)


def upgrade() -> None:
    op.create_table(
        "usuarios",
        _id(),
        sa.Column("username", sa.String, nullable=False),
        sa.Column("rol", rolenum, nullable=False),
        sa.Column("hashed_password", sa.String, nullable=False),
    )
    op.create_index("ix_usuarios_username", "usuarios", ["username"], unique=True)

    op.create_table(
        "productos",
        _id(),
        sa.Column("nombre", sa.String, nullable=False, index=True),
        sa.Column("precio_venta", sa.Float, nullable=False),
        sa.Column("stock_mostrador", sa.Integer, nullable=False),
    )
    op.create_table(
        "materias_primas",
        _id(),
        sa.Column("nombre", sa.String, nullable=False, index=True),
        sa.Column("stock_actual_kg", sa.Float, nullable=False),
        sa.Column("unidad_medida", sa.String, nullable=False),
        sa.Column("costo_unitario_actual", sa.Float, nullable=False, server_default="0.0"),
    )
    op.create_table(
        "proveedores",
        _id(),
        sa.Column("nombre", sa.String, nullable=False, index=True),
        sa.Column("cuit", sa.String),
        sa.Column("telefono", sa.String),
        sa.Column("direccion", sa.String),
        sa.Column("notas", sa.String),
    )
    op.create_table(
        "gastos_varios",
        _id(),
        sa.Column("concepto", sa.String, nullable=False),
        sa.Column("monto", sa.Float, nullable=False),
        sa.Column("fecha", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "turnos",
        _id(),
        sa.Column("usuario_id", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("fecha_apertura", sa.DateTime(timezone=True), nullable=False),
        sa.Column("efectivo_inicial", sa.Float, nullable=False),
        sa.Column("fecha_cierre", sa.DateTime(timezone=True)),
        sa.Column("estado", estadoturnoenum, nullable=False),
    )
    op.create_table(
        "ventas",
        _id(),
        sa.Column("turno_id", sa.Integer, sa.ForeignKey("turnos.id"), nullable=False),
        sa.Column("monto", sa.Float, nullable=False),
    )
    op.create_table(
        "detalles_venta",
        _id(),
        sa.Column("venta_id", sa.Integer, sa.ForeignKey("ventas.id"), nullable=False),
        sa.Column("producto_id", sa.Integer, sa.ForeignKey("productos.id"), nullable=False),
        sa.Column("cantidad", sa.Integer, nullable=False),
        sa.Column("subtotal", sa.Float, nullable=False),
    )
    op.create_table(
        "arqueos",
        _id(),
        sa.Column("turno_id", sa.Integer, sa.ForeignKey("turnos.id"), nullable=False, unique=True),
        sa.Column("monto_sistema", sa.Float, nullable=False),
        sa.Column("monto_declarado", sa.Float, nullable=False),
        sa.Column("diferencia", sa.Float, nullable=False),
    )
    op.create_table(
        "recetas_insumos",
        _id(),
        sa.Column("producto_id", sa.Integer, sa.ForeignKey("productos.id"), nullable=False),
        sa.Column("materia_prima_id", sa.Integer, sa.ForeignKey("materias_primas.id"), nullable=False),
        sa.Column("cantidad_necesaria", sa.Float, nullable=False),
    )
    op.create_table(
        "lotes_produccion",
        _id(),
        sa.Column("producto_id", sa.Integer, sa.ForeignKey("productos.id"), nullable=False),
        sa.Column("usuario_id", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("cantidad_producida", sa.Integer, nullable=False),
        sa.Column("fecha_hora", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "mermas",
        _id(),
        sa.Column("producto_id", sa.Integer, sa.ForeignKey("productos.id"), nullable=False),
        sa.Column("usuario_id", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("cantidad_perdida", sa.Integer, nullable=False),
        sa.Column("motivo", sa.String, nullable=False),
        sa.Column("fecha_hora", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "compras_materias_primas",
        _id(),
        sa.Column("proveedor_id", sa.Integer, sa.ForeignKey("proveedores.id"), nullable=False),
        sa.Column("materia_prima_id", sa.Integer, sa.ForeignKey("materias_primas.id"), nullable=False),
        sa.Column("cantidad_comprada", sa.Float, nullable=False),
        sa.Column("precio_total", sa.Float, nullable=False),
        sa.Column("fecha", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    for tabla in (
        "compras_materias_primas", "mermas", "lotes_produccion", "recetas_insumos", "arqueos",
        "detalles_venta", "ventas", "turnos", "gastos_varios", "proveedores", "materias_primas",
        "productos", "usuarios",
    ):
        op.drop_table(tabla)
    estadoturnoenum.drop(op.get_bind(), checkfirst=True)
    rolenum.drop(op.get_bind(), checkfirst=True)
