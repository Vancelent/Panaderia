from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.database import engine, Base
from app.routers import shifts
# Importamos modelos para que SQLAlchemy los registre y pueda crear las tablas
from app.models import user, shift

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Se ejecuta al iniciar la aplicación.
    # En desarrollo esto crea las tablas automáticamente.
    async with engine.begin() as conn:
        # await conn.run_sync(Base.metadata.drop_all) # Descomentar para resetear la base de datos
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Al cerrarse la aplicación
    await engine.dispose()

app = FastAPI(
    title="ERP/POS Panadería Inteligente", 
    description="Backend para gestión local enfocado en el Arqueo Ciego, balance de masas y seguridad.",
    version="1.0.0",
    lifespan=lifespan
)

# Registramos las Rutas
app.include_router(shifts.router)

@app.get("/", tags=["Hello World"])
def read_root():
    return {
        "message": "Bienvenido a la API del ERP/POS de la Panadería",
        "status": "Online"
    }
