import os
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

# La configuración debe existir antes de importar la app.
_tmp = Path(tempfile.mkdtemp())
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_tmp / 'test.db'}")
os.environ["JWT_SECRET"] = "test-secret-" + "x" * 40
os.environ["ENV"] = "test"
os.environ["COOKIE_SECURE"] = "false"

from fastapi.testclient import TestClient  # noqa: E402

from app.api.v1.auth import get_limiter  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, get_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import MateriaPrima, Producto, RecetaInsumo, RolEnum, Usuario  # noqa: E402

PASSWORD = "clave-segura-123"


@pytest.fixture(scope="session", autouse=True)
def _schema():
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def _limpiar_tablas():
    yield
    engine = get_engine()
    with engine.begin() as conn:
        for tabla in reversed(Base.metadata.sorted_tables):
            conn.execute(tabla.delete())
    get_limiter.cache_clear()


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


def crear_usuario(username: str, rol: RolEnum, password: str = PASSWORD) -> Usuario:
    with SessionLocal() as s:
        u = Usuario(username=username, rol=rol, hashed_password=hash_password(password))
        s.add(u)
        s.commit()
        return u


class Cliente(TestClient):
    """TestClient que reenvía el token CSRF como hace el frontend."""

    def request(self, method, url, **kwargs):
        csrf = self.cookies.get("panaderia_csrf")
        if csrf:
            headers = dict(kwargs.pop("headers", None) or {})
            headers.setdefault("X-CSRF-Token", csrf)
            kwargs["headers"] = headers
        return super().request(method, url, **kwargs)


def login(username: str, password: str = PASSWORD) -> Cliente:
    c = Cliente(app)
    r = c.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture
def anonimo():
    return Cliente(app)


@pytest.fixture
def como():
    """como(RolEnum.VENDEDORA) -> cliente HTTP autenticado con ese rol."""
    contador = {"n": 0}

    def _factory(rol: RolEnum, username: str | None = None) -> Cliente:
        contador["n"] += 1
        username = username or f"{rol.name.lower()}{contador['n']}"
        crear_usuario(username, rol)
        return login(username)

    return _factory


@pytest.fixture
def catalogo(db):
    """Dos productos y una receta: Pan (con harina) y Medialuna (sin receta)."""
    harina = MateriaPrima(nombre="Harina", unidad_medida="kg", stock_actual=Decimal("10"),
                          costo_unitario_actual=Decimal("500"))
    pan = Producto(nombre="Pan", precio_venta=Decimal("100.50"), stock_mostrador=10)
    medialuna = Producto(nombre="Medialuna", precio_venta=Decimal("80"), stock_mostrador=5)
    db.add_all([harina, pan, medialuna])
    db.flush()
    db.add(RecetaInsumo(producto_id=pan.id, materia_prima_id=harina.id,
                        cantidad_necesaria=Decimal("0.25")))
    db.commit()
    return {"harina": harina.id, "pan": pan.id, "medialuna": medialuna.id}
