"""Modernización v2: dinero en NUMERIC, auditoría de ventas, pedidos y clientes.

- Float -> Numeric en todos los importes y cantidades (sin pérdida: se redondea
  a 2 decimales en dinero, 3-4 en insumos).
- Ventas: fecha, usuario, método de pago, cliente. Se completan los datos
  existentes a partir del turno (fecha de apertura / cajero) y EFECTIVO.
- Detalle de venta: precio_unitario congelado (subtotal / cantidad).
- Usuarios: activo, token_version, nombre, creado_en.
- Un solo turno ABIERTO por usuario (índice único parcial).
- Nuevas tablas: clientes, pedidos, detalles_pedido.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-24
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

metodopagoenum = sa.Enum("EFECTIVO", "TARJETA", "TRANSFERENCIA", name="metodopagoenum")
estadopedidoenum = sa.Enum(
    "PENDIENTE", "EN_PREPARACION", "LISTO", "ENTREGADO", "CANCELADO", name="estadopedidoenum"
)

DINERO = sa.Numeric(12, 2)
CANTIDAD = sa.Numeric(12, 3)
COSTO = sa.Numeric(14, 4)
TS = sa.DateTime(timezone=True)

TABLAS_CON_IX_ID = [
    "arqueos", "compras_materias_primas", "detalles_venta", "gastos_varios", "lotes_produccion",
    "materias_primas", "mermas", "productos", "proveedores", "recetas_insumos", "turnos",
    "usuarios", "ventas",
]


def _a_numeric(tabla: str, columna: str, tipo: sa.Numeric) -> None:
    op.alter_column(
        tabla, columna, type_=tipo, existing_nullable=False,
        postgresql_using=f"round({columna}::numeric, {tipo.scale})",
    )


def _varchar(tabla: str, columna: str, largo: int, nullable: bool = False) -> None:
    op.alter_column(tabla, columna, type_=sa.String(largo), existing_nullable=nullable)


def upgrade() -> None:
    # El índice de la PK ya cubre id; estos índices extra eran redundantes.
    for tabla in TABLAS_CON_IX_ID:
        op.drop_index(f"ix_{tabla}_id", table_name=tabla)

    # ---------- usuarios ----------
    _varchar("usuarios", "username", 50)
    _varchar("usuarios", "hashed_password", 255)
    op.add_column("usuarios", sa.Column("nombre", sa.String(100)))
    op.add_column("usuarios", sa.Column("activo", sa.Boolean, nullable=False, server_default="true"))
    op.add_column("usuarios", sa.Column("token_version", sa.Integer, nullable=False, server_default="0"))
    op.add_column("usuarios", sa.Column("creado_en", TS, nullable=False, server_default=sa.func.now()))

    # ---------- productos / insumos ----------
    _varchar("productos", "nombre", 120)
    _a_numeric("productos", "precio_venta", DINERO)
    op.add_column("productos", sa.Column("categoria", sa.String(60)))
    op.add_column("productos", sa.Column("stock_minimo", sa.Integer, nullable=False, server_default="0"))
    op.add_column("productos", sa.Column("activo", sa.Boolean, nullable=False, server_default="true"))

    _varchar("materias_primas", "nombre", 120)
    _varchar("materias_primas", "unidad_medida", 20)
    op.alter_column("materias_primas", "stock_actual_kg", new_column_name="stock_actual")
    _a_numeric("materias_primas", "stock_actual", CANTIDAD)
    op.alter_column("materias_primas", "costo_unitario_actual", server_default=None)
    _a_numeric("materias_primas", "costo_unitario_actual", COSTO)
    op.alter_column("materias_primas", "costo_unitario_actual", server_default="0")
    op.add_column(
        "materias_primas", sa.Column("stock_minimo", CANTIDAD, nullable=False, server_default="0")
    )

    _a_numeric("recetas_insumos", "cantidad_necesaria", COSTO)
    op.create_unique_constraint(
        "recetas_insumos_producto_id_materia_prima_id_key",
        "recetas_insumos", ["producto_id", "materia_prima_id"],
    )
    op.create_index("ix_recetas_insumos_producto_id", "recetas_insumos", ["producto_id"])

    op.create_index("ix_lotes_produccion_producto_id", "lotes_produccion", ["producto_id"])
    op.create_index("ix_lotes_produccion_fecha_hora", "lotes_produccion", ["fecha_hora"])
    _varchar("mermas", "motivo", 200)
    op.create_index("ix_mermas_producto_id", "mermas", ["producto_id"])
    op.create_index("ix_mermas_fecha_hora", "mermas", ["fecha_hora"])

    # ---------- turnos / arqueos ----------
    _a_numeric("turnos", "efectivo_inicial", DINERO)
    op.create_index("ix_turnos_usuario_id", "turnos", ["usuario_id"])
    op.create_index(
        "uq_turno_abierto_por_usuario", "turnos", ["usuario_id"], unique=True,
        postgresql_where=sa.text("estado = 'ABIERTO'"),
    )
    for col in ("monto_sistema", "monto_declarado", "diferencia"):
        _a_numeric("arqueos", col, DINERO)
    op.add_column("arqueos", sa.Column("ventas_efectivo", DINERO))
    op.add_column("arqueos", sa.Column("ventas_otros_medios", DINERO))
    op.add_column("arqueos", sa.Column("fecha", TS))
    op.execute(
        "UPDATE arqueos a SET fecha = t.fecha_cierre FROM turnos t WHERE t.id = a.turno_id"
    )

    # ---------- clientes (antes que ventas, por la FK) ----------
    op.create_table(
        "clientes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("nombre", sa.String(120), nullable=False, index=True),
        sa.Column("telefono", sa.String(40)),
        sa.Column("email", sa.String(120)),
        sa.Column("direccion", sa.String(200)),
        sa.Column("notas", sa.Text),
        sa.Column("activo", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("creado_en", TS, nullable=False, server_default=sa.func.now()),
    )

    # ---------- ventas ----------
    metodopagoenum.create(op.get_bind(), checkfirst=True)
    _a_numeric("ventas", "monto", DINERO)
    op.add_column("ventas", sa.Column("usuario_id", sa.Integer, sa.ForeignKey("usuarios.id")))
    op.add_column("ventas", sa.Column("cliente_id", sa.Integer, sa.ForeignKey("clientes.id")))
    op.add_column("ventas", sa.Column("fecha", TS))
    op.add_column(
        "ventas",
        sa.Column("metodo_pago", metodopagoenum, nullable=False, server_default="EFECTIVO"),
    )
    op.execute(
        "UPDATE ventas v SET usuario_id = t.usuario_id, fecha = t.fecha_apertura "
        "FROM turnos t WHERE t.id = v.turno_id"
    )
    op.alter_column("ventas", "fecha", nullable=False)
    op.alter_column("ventas", "metodo_pago", server_default=None)
    op.create_index("ix_ventas_turno_id", "ventas", ["turno_id"])
    op.create_index("ix_ventas_cliente_id", "ventas", ["cliente_id"])
    op.create_index("ix_ventas_fecha", "ventas", ["fecha"])

    _a_numeric("detalles_venta", "subtotal", DINERO)
    op.add_column("detalles_venta", sa.Column("precio_unitario", DINERO))
    op.execute(
        "UPDATE detalles_venta SET precio_unitario = round(subtotal / NULLIF(cantidad, 0), 2)"
    )
    op.execute("UPDATE detalles_venta SET precio_unitario = 0 WHERE precio_unitario IS NULL")
    op.alter_column("detalles_venta", "precio_unitario", nullable=False)
    op.create_index("ix_detalles_venta_venta_id", "detalles_venta", ["venta_id"])
    op.create_index("ix_detalles_venta_producto_id", "detalles_venta", ["producto_id"])

    # ---------- compras / gastos / proveedores ----------
    _varchar("proveedores", "nombre", 120)
    _varchar("proveedores", "cuit", 20, nullable=True)
    _varchar("proveedores", "telefono", 40, nullable=True)
    _varchar("proveedores", "direccion", 200, nullable=True)
    op.alter_column("proveedores", "notas", type_=sa.Text, existing_nullable=True)
    _a_numeric("compras_materias_primas", "cantidad_comprada", CANTIDAD)
    _a_numeric("compras_materias_primas", "precio_total", DINERO)
    op.create_index("ix_compras_materias_primas_proveedor_id", "compras_materias_primas", ["proveedor_id"])
    op.create_index(
        "ix_compras_materias_primas_materia_prima_id", "compras_materias_primas", ["materia_prima_id"]
    )
    op.create_index("ix_compras_materias_primas_fecha", "compras_materias_primas", ["fecha"])
    _varchar("gastos_varios", "concepto", 200)
    _a_numeric("gastos_varios", "monto", DINERO)
    op.create_index("ix_gastos_varios_fecha", "gastos_varios", ["fecha"])

    # ---------- pedidos ----------
    op.create_table(
        "pedidos",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("cliente_id", sa.Integer, sa.ForeignKey("clientes.id"), index=True),
        sa.Column("contacto", sa.String(120)),
        sa.Column("estado", estadopedidoenum, nullable=False, index=True),
        sa.Column("fecha_entrega", TS, nullable=False, index=True),
        sa.Column("notas", sa.Text),
        sa.Column("total", DINERO, nullable=False),
        sa.Column("creado_por_id", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("creado_en", TS, nullable=False),
        sa.Column("actualizado_en", TS, nullable=False),
        sa.Column("venta_id", sa.Integer, sa.ForeignKey("ventas.id")),
    )
    op.create_table(
        "detalles_pedido",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("pedido_id", sa.Integer, sa.ForeignKey("pedidos.id"), nullable=False, index=True),
        sa.Column("producto_id", sa.Integer, sa.ForeignKey("productos.id"), nullable=False),
        sa.Column("cantidad", sa.Integer, nullable=False),
        sa.Column("precio_unitario", DINERO, nullable=False),
        sa.Column("subtotal", DINERO, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("detalles_pedido")
    op.drop_table("pedidos")
    estadopedidoenum.drop(op.get_bind(), checkfirst=True)

    for idx, tabla in [
        ("ix_gastos_varios_fecha", "gastos_varios"),
        ("ix_compras_materias_primas_fecha", "compras_materias_primas"),
        ("ix_compras_materias_primas_materia_prima_id", "compras_materias_primas"),
        ("ix_compras_materias_primas_proveedor_id", "compras_materias_primas"),
        ("ix_detalles_venta_producto_id", "detalles_venta"),
        ("ix_detalles_venta_venta_id", "detalles_venta"),
        ("ix_ventas_fecha", "ventas"),
        ("ix_ventas_cliente_id", "ventas"),
        ("ix_ventas_turno_id", "ventas"),
        ("uq_turno_abierto_por_usuario", "turnos"),
        ("ix_turnos_usuario_id", "turnos"),
        ("ix_mermas_fecha_hora", "mermas"),
        ("ix_mermas_producto_id", "mermas"),
        ("ix_lotes_produccion_fecha_hora", "lotes_produccion"),
        ("ix_lotes_produccion_producto_id", "lotes_produccion"),
        ("ix_recetas_insumos_producto_id", "recetas_insumos"),
    ]:
        op.drop_index(idx, table_name=tabla)

    op.drop_column("detalles_venta", "precio_unitario")
    for col in ("metodo_pago", "fecha", "cliente_id", "usuario_id"):
        op.drop_column("ventas", col)
    metodopagoenum.drop(op.get_bind(), checkfirst=True)
    op.drop_table("clientes")
    for col in ("fecha", "ventas_otros_medios", "ventas_efectivo"):
        op.drop_column("arqueos", col)
    op.drop_constraint("recetas_insumos_producto_id_materia_prima_id_key", "recetas_insumos")
    op.drop_column("materias_primas", "stock_minimo")
    op.alter_column("materias_primas", "stock_actual", new_column_name="stock_actual_kg")
    for col in ("activo", "stock_minimo", "categoria"):
        op.drop_column("productos", col)
    for col in ("creado_en", "token_version", "activo", "nombre"):
        op.drop_column("usuarios", col)

    float_cols = {
        "productos": ["precio_venta"], "materias_primas": ["stock_actual_kg", "costo_unitario_actual"],
        "recetas_insumos": ["cantidad_necesaria"], "turnos": ["efectivo_inicial"],
        "arqueos": ["monto_sistema", "monto_declarado", "diferencia"], "ventas": ["monto"],
        "detalles_venta": ["subtotal"], "compras_materias_primas": ["cantidad_comprada", "precio_total"],
        "gastos_varios": ["monto"],
    }
    for tabla, cols in float_cols.items():
        for col in cols:
            op.alter_column(tabla, col, type_=sa.Float, postgresql_using=f"{col}::double precision")
    for tabla in TABLAS_CON_IX_ID:
        op.create_index(f"ix_{tabla}_id", tabla, ["id"])
