from database import engine
from sqlalchemy import text

try:
    with engine.begin() as conn:
        # Create ENUM type first if not exists
        try:
            conn.execute(text("CREATE TYPE metodopagoenum AS ENUM ('Efectivo', 'Tarjeta', 'Transferencia');"))
        except Exception as e:
            print("Enum might already exist:", e)

        # Add column to ventas
        conn.execute(text("ALTER TABLE ventas ADD COLUMN IF NOT EXISTS metodo_pago metodopagoenum NOT NULL DEFAULT 'Efectivo';"))
        
        # Add column to compras_materias_primas
        conn.execute(text("ALTER TABLE compras_materias_primas ADD COLUMN IF NOT EXISTS metodo_pago metodopagoenum NOT NULL DEFAULT 'Efectivo';"))
        
        # Add column to gastos_varios
        conn.execute(text("ALTER TABLE gastos_varios ADD COLUMN IF NOT EXISTS metodo_pago metodopagoenum NOT NULL DEFAULT 'Efectivo';"))

    print("Migration successful")
except Exception as e:
    print(f"Migration error: {e}")
