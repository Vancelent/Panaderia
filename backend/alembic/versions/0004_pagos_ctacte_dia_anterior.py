"""Pagos múltiples, cuenta corriente, puntos de entrega y pan del día anterior.

- ventas_pagos (nueva) con BACKFILL: un pago por cada venta existente, con su método y monto.
  `ventas.metodo_pago` se conserva como medio principal.
- arqueos.cobros_efectivo: cobros de cuenta corriente en efectivo dentro del turno.
- clientes: saldo_cuenta_corriente (Dinero) y cuit.
- productos: codigo (único), producto_base_id (variante "día anterior", única por base) y
  stock_reservado con CHECK (0 <= reservado <= stock_mostrador). Lo usa el reparto (Fase 2).
- Nuevas: conversiones_dia_anterior, puntos_entrega, descuentos_punto, plantillas_entrega,
  movimientos_cuenta_corriente.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-01
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

DINERO = sa.Numeric(12, 2)
TS = sa.DateTime(timezone=True)

# Los tipos ya existen (0002 y 0003): acá solo se referencian
metodopago = postgresql.ENUM(
    "EFECTIVO", "TARJETA", "TRANSFERENCIA", "QR", "CUENTA_CORRIENTE",
    name="metodopagoenum", create_type=False,
)
estadopago = postgresql.ENUM(
    "APROBADO", "PENDIENTE", "RECHAZADO", name="estadopagoenum", create_type=False
)
tipomovimiento = postgresql.ENUM(
    "CARGO", "PAGO", "NOTA_CREDITO", "AJUSTE", name="tipomovimientoctacteenum", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()

    # La restricción de reserva exige stock >= 0: si hubiera filas inválidas, avisar en
    # lugar de corregirlas en silencio (es dinero y mercadería).
    negativos = bind.execute(sa.text("SELECT count(*) FROM productos WHERE stock_mostrador < 0")).scalar()
    if negativos:
        raise RuntimeError(
            f"Hay {negativos} producto(s) con stock_mostrador negativo. "
            "Corregilos (ajuste de stock) y volvé a migrar."
        )

    # ---------- clientes ----------
    op.add_column(
        "clientes", sa.Column("saldo_cuenta_corriente", DINERO, nullable=False, server_default="0")
    )
    op.add_column("clientes", sa.Column("cuit", sa.String(20)))

    # ---------- productos ----------
    op.add_column("productos", sa.Column("codigo", sa.String(12)))
    op.create_unique_constraint("productos_codigo_key", "productos", ["codigo"])
    op.add_column("productos", sa.Column("producto_base_id", sa.Integer))
    op.create_foreign_key(
        "productos_producto_base_id_fkey", "productos", "productos", ["producto_base_id"], ["id"]
    )
    op.create_unique_constraint("productos_producto_base_id_key", "productos", ["producto_base_id"])
    op.add_column(
        "productos", sa.Column("stock_reservado", sa.Integer, nullable=False, server_default="0")
    )
    op.create_check_constraint(
        "ck_productos_reserva_valida",
        "productos",
        "stock_reservado >= 0 AND stock_reservado <= stock_mostrador",
    )

    # ---------- arqueos ----------
    op.add_column("arqueos", sa.Column("cobros_efectivo", DINERO))

    # ---------- ventas_pagos + backfill ----------
    op.create_table(
        "ventas_pagos",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("venta_id", sa.Integer, sa.ForeignKey("ventas.id"), nullable=False, index=True),
        sa.Column("metodo_pago", metodopago, nullable=False),
        sa.Column("monto", DINERO, nullable=False),
        sa.Column("referencia", sa.String(120)),
        sa.Column("estado", estadopago, nullable=False),
        sa.Column("proveedor", sa.String(60)),
        sa.Column("fecha", TS, nullable=False),
        sa.CheckConstraint("monto > 0", name="ck_venta_pago_monto_positivo"),
    )
    # Un pago aprobado por cada venta existente, por el total y con su medio original.
    op.execute(
        """
        INSERT INTO ventas_pagos (venta_id, metodo_pago, monto, estado, fecha)
        SELECT id, metodo_pago, monto, CAST('APROBADO' AS estadopagoenum), fecha
        FROM ventas
        WHERE monto > 0
        """
    )

    # ---------- puntos de entrega ----------
    op.create_table(
        "puntos_entrega",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("cliente_id", sa.Integer, sa.ForeignKey("clientes.id"), nullable=False, index=True),
        sa.Column("nombre", sa.String(120), nullable=False, index=True),
        sa.Column("direccion", sa.String(200)),
        sa.Column("latitud", sa.Numeric(9, 6)),
        sa.Column("longitud", sa.Numeric(9, 6)),
        sa.Column("ventana_desde", sa.Time),
        sa.Column("ventana_hasta", sa.Time),
        sa.Column("contacto", sa.String(120)),
        sa.Column("notas", sa.Text),
        sa.Column("repartidor_habitual_id", sa.Integer, sa.ForeignKey("usuarios.id")),
        sa.Column("activo", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("creado_en", TS, nullable=False),
    )
    op.create_table(
        "descuentos_punto",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "punto_entrega_id", sa.Integer, sa.ForeignKey("puntos_entrega.id"), nullable=False, index=True
        ),
        sa.Column("producto_id", sa.Integer, sa.ForeignKey("productos.id")),
        sa.Column("porcentaje", sa.Numeric(5, 2), nullable=False),
        sa.Column("motivo", sa.String(120), nullable=False),
        sa.Column("vigente_desde", sa.Date),
        sa.Column("vigente_hasta", sa.Date),
        sa.Column("activo", sa.Boolean, nullable=False, server_default="true"),
        sa.CheckConstraint("porcentaje > 0 AND porcentaje <= 100", name="ck_descuento_porcentaje"),
    )
    op.create_table(
        "plantillas_entrega",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "punto_entrega_id", sa.Integer, sa.ForeignKey("puntos_entrega.id"), nullable=False, index=True
        ),
        sa.Column("dia_semana", sa.SmallInteger, nullable=False),
        sa.Column("producto_id", sa.Integer, sa.ForeignKey("productos.id"), nullable=False),
        sa.Column("cantidad", sa.Integer, nullable=False),
        sa.UniqueConstraint("punto_entrega_id", "dia_semana", "producto_id"),
        sa.CheckConstraint("dia_semana >= 0 AND dia_semana <= 6", name="ck_plantilla_dia"),
        sa.CheckConstraint("cantidad > 0", name="ck_plantilla_cantidad"),
    )

    # ---------- cuenta corriente ----------
    op.create_table(
        "movimientos_cuenta_corriente",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("cliente_id", sa.Integer, sa.ForeignKey("clientes.id"), nullable=False, index=True),
        sa.Column("punto_entrega_id", sa.Integer, sa.ForeignKey("puntos_entrega.id")),
        sa.Column("tipo", tipomovimiento, nullable=False),
        sa.Column("importe", DINERO, nullable=False),
        sa.Column("metodo_pago", metodopago),
        sa.Column("referencia", sa.String(120)),
        sa.Column("venta_id", sa.Integer, sa.ForeignKey("ventas.id")),
        sa.Column("turno_id", sa.Integer, sa.ForeignKey("turnos.id"), index=True),
        sa.Column("corrige_id", sa.Integer, sa.ForeignKey("movimientos_cuenta_corriente.id")),
        sa.Column("operacion_id", sa.Uuid, unique=True),
        sa.Column("usuario_id", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("fecha", TS, nullable=False, index=True),
        sa.Column("observacion", sa.String(200)),
        sa.CheckConstraint("importe <> 0", name="ck_movimiento_importe_no_cero"),
    )

    # ---------- pan del día anterior ----------
    op.create_table(
        "conversiones_dia_anterior",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "producto_base_id", sa.Integer, sa.ForeignKey("productos.id"), nullable=False, index=True
        ),
        sa.Column("variante_id", sa.Integer, sa.ForeignKey("productos.id"), nullable=False),
        sa.Column("cantidad", sa.Integer, nullable=False),
        sa.Column("usuario_id", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("fecha", TS, nullable=False, index=True),
        sa.Column("motivo", sa.String(200)),
        sa.Column(
            "revierte_id", sa.Integer, sa.ForeignKey("conversiones_dia_anterior.id"), unique=True
        ),
        sa.CheckConstraint("cantidad > 0", name="ck_conversion_cantidad_positiva"),
    )


def downgrade() -> None:
    op.drop_table("conversiones_dia_anterior")
    op.drop_table("movimientos_cuenta_corriente")
    op.drop_table("plantillas_entrega")
    op.drop_table("descuentos_punto")
    op.drop_table("puntos_entrega")
    # ventas_pagos se descarta: ventas.metodo_pago (medio principal) conserva el medio de cada
    # venta; un pago mixto quedaría reducido a su medio mayoritario.
    op.drop_table("ventas_pagos")
    op.drop_column("arqueos", "cobros_efectivo")

    op.drop_constraint("ck_productos_reserva_valida", "productos", type_="check")
    op.drop_column("productos", "stock_reservado")
    op.drop_constraint("productos_producto_base_id_key", "productos", type_="unique")
    op.drop_constraint("productos_producto_base_id_fkey", "productos", type_="foreignkey")
    op.drop_column("productos", "producto_base_id")
    op.drop_constraint("productos_codigo_key", "productos", type_="unique")
    op.drop_column("productos", "codigo")

    op.drop_column("clientes", "cuit")
    op.drop_column("clientes", "saldo_cuenta_corriente")
