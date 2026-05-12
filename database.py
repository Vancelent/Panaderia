import os
import time
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker, declarative_base

# Leemos la variable de entorno que inyecta Docker con la URL de PostgreSQL
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:panaderosecreto@db:5432/erp_panaderia")

# Motor de conexión síncrona a la base de datos compatible con psycopg2-binary
engine = create_engine(SQLALCHEMY_DATABASE_URL)

# Lógica de reintentos para esperar a que PostgreSQL inicie en Docker
MAX_RETRIES = 5
RETRY_DELAY = 2

for attempt in range(MAX_RETRIES):
    try:
        with engine.connect() as conn:
            print(f"Conexión exitosa a PostgreSQL en el intento {attempt + 1}")
            break
    except OperationalError as e:
        if attempt < MAX_RETRIES - 1:
            print(f"Base de datos no disponible (Intento {attempt + 1}/{MAX_RETRIES}). Reintentando en {RETRY_DELAY} segundos...")
            time.sleep(RETRY_DELAY)
        else:
            print("Fallo crítico: No se pudo establecer conexión con PostgreSQL.")
            raise e

# Fábrica de sesiones para interactuar con la Base de Datos
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Clase base declarativa de la que heredarán todos los Modelos
Base = declarative_base()

# Dependencia para uso en los endpoints de FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
