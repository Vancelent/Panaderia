"""Reparto: hojas de ruta, entregas, recorrido GPS, remitos e idempotencia (Fase 2 del RFC-001).

- rolenum: + REPARTIDOR
- Enums nuevos: tipoturnoenum, origenventaenum, estadohojarutaenum, estadoentregaenum,
  tipoeventoentregaenum, tipoeventorecorridoenum
- turnos.tipo (MOSTRADOR | REPARTO); el índice único de turno abierto pasa a (usuario_id, tipo)
- ventas.origen (MOSTRADOR | PEDIDO | REPARTO, con backfill) y ventas.punto_entrega_id
- numeradores (con la fila de remitos) y operaciones_idempotentes
- hojas_ruta, hojas_ruta_items, entregas, entregas_items, entregas_eventos
- recorrido_puntos PARTICIONADA por mes (la partición del mes en curso, la del siguiente y una
  DEFAULT) y recorrido_eventos. El mantenimiento diario (`python -m app.cli mantenimiento-gps`)
  crea las particiones futuras y elimina las de más de 90 días.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-02
"""

from datetime import UTC, date, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

DINERO = sa.Numeric(12, 2)
TS = sa.DateTime(timezone=True)
COORD = sa.Numeric(9, 6)

NUEVOS_ENUMS = {
    "tipoturnoenum": ("MOSTRADOR", "REPARTO"),
    "origenventaenum": ("MOSTRADOR", "PEDIDO", "REPARTO"),
    "estadohojarutaenum": ("BORRADOR", "CONFIRMADA", "CARGADA", "EN_RUTA", "RENDIDA", "ANULADA"),
    "estadoentregaenum": ("PENDIENTE", "EN_LOCAL", "ENTREGADA", "PARCIAL", "NO_ENTREGADA"),
    "tipoeventoentregaenum": ("CHECK_IN", "CONFIRMADA", "NO_ENTREGADA", "NOTA"),
    "tipoeventorecorridoenum": ("GPS_SIN_SENAL", "PERMISO_REVOCADO", "TRAZA_INTERRUMPIDA"),
}


def _enum(nombre: str) -> postgresql.ENUM:
    """Referencia a un tipo ya creado (create_type=False)."""
    return postgresql.ENUM(*NUEVOS_ENUMS[nombre], name=nombre, create_type=False)


def _mes_siguiente(d: date) -> date:
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def upgrade() -> None:
    bind = op.get_bind()

    # El valor nuevo se agrega fuera de la transacción de la migración
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE rolenum ADD VALUE IF NOT EXISTS 'REPARTIDOR'")
    for nombre, valores in NUEVOS_ENUMS.items():
        postgresql.ENUM(*valores, name=nombre).create(bind, checkfirst=True)

    # ---------- turnos ----------
    op.add_column(
        "turnos",
        sa.Column("tipo", _enum("tipoturnoenum"), nullable=False, server_default="MOSTRADOR"),
    )
    op.drop_index("uq_turno_abierto_por_usuario", table_name="turnos")
    op.create_index(
        "uq_turno_abierto_por_usuario", "turnos", ["usuario_id", "tipo"], unique=True,
        postgresql_where=sa.text("estado = 'ABIERTO'"),
    )

    # ---------- ventas ----------
    op.add_column(
        "ventas",
        sa.Column("origen", _enum("origenventaenum"), nullable=False, server_default="MOSTRADOR"),
    )
    op.add_column("ventas", sa.Column("punto_entrega_id", sa.Integer, sa.ForeignKey("puntos_entrega.id")))
    op.create_index("ix_ventas_punto_entrega_id", "ventas", ["punto_entrega_id"])
    # Las ventas que salieron de entregar un pedido se distinguen de las de mostrador
    op.execute(
        "UPDATE ventas SET origen = CAST('PEDIDO' AS origenventaenum) "
        "WHERE id IN (SELECT venta_id FROM pedidos WHERE venta_id IS NOT NULL)"
    )

    # ---------- soporte ----------
    op.create_table(
        "numeradores",
        sa.Column("tipo", sa.String(20), primary_key=True),
        sa.Column("ultimo_numero", sa.Integer, nullable=False, server_default="0"),
    )
    op.execute("INSERT INTO numeradores (tipo, ultimo_numero) VALUES ('remito', 0)")
    op.create_table(
        "operaciones_idempotentes",
        sa.Column("operacion_id", sa.Uuid, primary_key=True),
        sa.Column("usuario_id", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("tipo", sa.String(40), nullable=False),
        sa.Column("respuesta", sa.JSON),
        sa.Column("creado_en", TS, nullable=False, index=True),
    )

    # ---------- hojas de ruta ----------
    op.create_table(
        "hojas_ruta",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("fecha", sa.Date, nullable=False, index=True),
        sa.Column("repartidor_id", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=False, index=True),
        sa.Column("turno_id", sa.Integer, sa.ForeignKey("turnos.id")),
        sa.Column("estado", _enum("estadohojarutaenum"), nullable=False, index=True),
        sa.Column("creado_por_id", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("creado_en", TS, nullable=False),
        sa.Column("confirmada_en", TS),
        sa.Column("cargada_en", TS),
        sa.Column("iniciada_en", TS),
        sa.Column("rendida_en", TS),
        sa.Column("distancia_sugerida_km", sa.Numeric(7, 2)),
        sa.Column("distancia_real_km", sa.Numeric(7, 2)),
    )
    op.create_table(
        "hojas_ruta_items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("hoja_id", sa.Integer, sa.ForeignKey("hojas_ruta.id"), nullable=False, index=True),
        sa.Column("producto_id", sa.Integer, sa.ForeignKey("productos.id"), nullable=False),
        sa.Column("cantidad_reservada", sa.Integer, nullable=False),
        sa.Column("cantidad_cargada", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cantidad_devuelta", sa.Integer, nullable=False, server_default="0"),
        sa.UniqueConstraint("hoja_id", "producto_id"),
        sa.CheckConstraint(
            "cantidad_reservada >= 0 AND cantidad_cargada >= 0 AND cantidad_devuelta >= 0",
            name="ck_hoja_item_cantidades",
        ),
    )
    op.create_table(
        "entregas",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("hoja_id", sa.Integer, sa.ForeignKey("hojas_ruta.id"), nullable=False, index=True),
        sa.Column("punto_entrega_id", sa.Integer, sa.ForeignKey("puntos_entrega.id"), nullable=False),
        sa.Column("orden_sugerido", sa.Integer, nullable=False),
        sa.Column("orden_real", sa.Integer),
        sa.Column("estado", _enum("estadoentregaenum"), nullable=False, index=True),
        sa.Column("venta_id", sa.Integer, sa.ForeignKey("ventas.id")),
        sa.Column("numero_remito", sa.Integer, unique=True),
        sa.Column("operacion_id", sa.Uuid, unique=True),
        sa.Column("latitud", COORD),
        sa.Column("longitud", COORD),
        sa.Column("confirmada_en_dispositivo", TS),
        sa.Column("recibida_en_servidor", TS),
        sa.Column("recibio_nombre", sa.String(120)),
        sa.Column("motivo_no_entrega", sa.String(200)),
        sa.UniqueConstraint("hoja_id", "punto_entrega_id"),
    )
    op.create_table(
        "entregas_items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("entrega_id", sa.Integer, sa.ForeignKey("entregas.id"), nullable=False, index=True),
        sa.Column("producto_id", sa.Integer, sa.ForeignKey("productos.id"), nullable=False),
        sa.Column("cantidad_planificada", sa.Integer, nullable=False),
        sa.Column("cantidad_entregada", sa.Integer, nullable=False, server_default="0"),
        sa.Column("precio_lista", DINERO, nullable=False),
        sa.Column("descuento_pct", sa.Numeric(5, 2)),
        sa.Column("precio_unitario", DINERO, nullable=False),
        sa.UniqueConstraint("entrega_id", "producto_id"),
        sa.CheckConstraint(
            "cantidad_planificada > 0 AND cantidad_entregada >= 0", name="ck_entrega_item_cantidades"
        ),
    )
    op.create_table(
        "entregas_eventos",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("entrega_id", sa.Integer, sa.ForeignKey("entregas.id"), nullable=False, index=True),
        sa.Column("tipo", _enum("tipoeventoentregaenum"), nullable=False),
        sa.Column("latitud", COORD),
        sa.Column("longitud", COORD),
        sa.Column("precision_m", sa.Numeric(7, 1)),
        sa.Column("registrado_en_dispositivo", TS),
        sa.Column("recibido_en_servidor", TS, nullable=False),
        sa.Column("usuario_id", sa.Integer, sa.ForeignKey("usuarios.id")),
        sa.Column("detalle", sa.String(200)),
    )

    # ---------- recorrido GPS ----------
    op.create_table(
        "recorrido_puntos",
        sa.Column("lote_id", sa.Uuid, nullable=False),
        sa.Column("registrado_en_dispositivo", TS, nullable=False),
        sa.Column("hoja_id", sa.Integer, sa.ForeignKey("hojas_ruta.id"), nullable=False),
        sa.Column("latitud", COORD, nullable=False),
        sa.Column("longitud", COORD, nullable=False),
        sa.Column("precision_m", sa.Numeric(7, 1)),
        sa.Column("recibido_en_servidor", TS, nullable=False),
        # PostgreSQL exige que la clave primaria incluya la de partición
        sa.PrimaryKeyConstraint("lote_id", "registrado_en_dispositivo"),
        postgresql_partition_by="RANGE (registrado_en_dispositivo)",
    )
    op.create_index(
        "ix_recorrido_hoja_fecha", "recorrido_puntos", ["hoja_id", "registrado_en_dispositivo"]
    )
    hoy = datetime.now(UTC).date().replace(day=1)
    for inicio in (hoy, _mes_siguiente(hoy)):
        fin = _mes_siguiente(inicio)
        op.execute(
            f"CREATE TABLE recorrido_puntos_{inicio:%Y_%m} PARTITION OF recorrido_puntos "
            # Límites en UTC explícito: sin esto dependerían de la zona horaria de la sesión
            f"FOR VALUES FROM ('{inicio.isoformat()} 00:00:00+00') TO ('{fin.isoformat()} 00:00:00+00')"
        )
    # Lo que llegue con una fecha fuera de rango (reloj muy desfasado) no se pierde
    op.execute("CREATE TABLE recorrido_puntos_default PARTITION OF recorrido_puntos DEFAULT")

    op.create_table(
        "recorrido_eventos",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("hoja_id", sa.Integer, sa.ForeignKey("hojas_ruta.id"), nullable=False, index=True),
        sa.Column("tipo", _enum("tipoeventorecorridoenum"), nullable=False),
        sa.Column("desde", TS, nullable=False),
        sa.Column("hasta", TS),
        sa.Column("recibido_en_servidor", TS, nullable=False, index=True),
        sa.UniqueConstraint("hoja_id", "tipo", "desde"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_table("recorrido_eventos")
    op.execute("DROP TABLE recorrido_puntos CASCADE")  # arrastra sus particiones
    op.drop_table("entregas_eventos")
    op.drop_table("entregas_items")
    op.drop_table("entregas")
    op.drop_table("hojas_ruta_items")
    op.drop_table("hojas_ruta")
    op.drop_table("operaciones_idempotentes")
    op.drop_table("numeradores")

    op.drop_index("ix_ventas_punto_entrega_id", table_name="ventas")
    op.drop_column("ventas", "punto_entrega_id")
    op.drop_column("ventas", "origen")

    op.drop_index("uq_turno_abierto_por_usuario", table_name="turnos")
    op.create_index(
        "uq_turno_abierto_por_usuario", "turnos", ["usuario_id"], unique=True,
        postgresql_where=sa.text("estado = 'ABIERTO'"),
    )
    op.drop_column("turnos", "tipo")

    for nombre, valores in reversed(list(NUEVOS_ENUMS.items())):
        postgresql.ENUM(*valores, name=nombre).drop(bind, checkfirst=True)
    # PostgreSQL no permite quitar un valor de un enum: REPARTIDOR queda en rolenum.
