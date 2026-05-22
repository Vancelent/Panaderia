from database import engine
from sqlalchemy import text

try:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE materias_primas ADD COLUMN IF NOT EXISTS costo_unitario_actual FLOAT NOT NULL DEFAULT 0.0;"))
        conn.commit()
    print("Migration successful")
except Exception as e:
    print(f"Migration error: {e}")
