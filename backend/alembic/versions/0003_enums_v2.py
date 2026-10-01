"""Enums v2: nuevos medios de pago y tipos para pagos y cuenta corriente.

Va separada de 0004 porque en PostgreSQL un valor agregado con ALTER TYPE ... ADD VALUE
no se puede usar dentro de la misma transacción que lo crea.

- metodopagoenum: + QR, + CUENTA_CORRIENTE
- estadopagoenum (nuevo): APROBADO, PENDIENTE, RECHAZADO
- tipomovimientoctacteenum (nuevo): CARGO, PAGO, NOTA_CREDITO, AJUSTE

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-01
"""

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

estadopagoenum = postgresql.ENUM("APROBADO", "PENDIENTE", "RECHAZADO", name="estadopagoenum")
tipomovimientoctacteenum = postgresql.ENUM(
    "CARGO", "PAGO", "NOTA_CREDITO", "AJUSTE", name="tipomovimientoctacteenum"
)


def upgrade() -> None:
    bind = op.get_bind()
    # ADD VALUE se ejecuta fuera de la transacción de la migración (autocommit)
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE metodopagoenum ADD VALUE IF NOT EXISTS 'QR'")
        op.execute("ALTER TYPE metodopagoenum ADD VALUE IF NOT EXISTS 'CUENTA_CORRIENTE'")
    estadopagoenum.create(bind, checkfirst=True)
    tipomovimientoctacteenum.create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    tipomovimientoctacteenum.drop(bind, checkfirst=True)
    estadopagoenum.drop(bind, checkfirst=True)
    # PostgreSQL no permite quitar valores de un enum: QR y CUENTA_CORRIENTE quedan en
    # metodopagoenum. Son inofensivos mientras ninguna fila los use (0004 ya se revirtió).
