import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

# Por defecto está configurado con SQLite asíncrono para que puedas correr el proyecto inmediatamente sin configuración extra.
# Para Producción con PostgreSQL (como se solicita en tu stack), usa la línea de abajo o configura la variable de entorno DATABASE_URL.
# SQLALCHEMY_DATABASE_URL = "postgresql+asyncpg://usuario:password@localhost:5432/panaderia"

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./panaderia.db")

engine = create_async_engine(SQLALCHEMY_DATABASE_URL, echo=False)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
