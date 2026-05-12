import enum
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class RoleEnum(str, enum.Enum):
    ADMIN = "admin"
    ENCARGADA = "encargada"
    VENDEDORA = "vendedora"
    PANADERO = "panadero"

class User(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    role: Mapped[RoleEnum] = mapped_column(SQLAlchemyEnum(RoleEnum), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)
