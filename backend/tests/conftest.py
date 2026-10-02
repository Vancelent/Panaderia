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
API = "/api/v1"


@pytest.fixture(scope="session", autouse=True)
def _schema():
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    if engine.dialect.name == "postgresql":
        # La tabla de la traza GPS está particionada: create_all solo crea la tabla madre.
        # En producción la partición DEFAULT la crea la migración 0005.
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "CREATE TABLE recorrido_puntos_default PARTITION OF recorrido_puntos DEFAULT"
            )
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


@pytest.fixture
def reparto(como, catalogo):
    """Un admin, un repartidor, un cliente con dos puntos de entrega y stock holgado."""
    admin = como(RolEnum.ADMIN, "dueno")
    crear_usuario("repa", RolEnum.REPARTIDOR)
    repa = login("repa")
    for pid, n in ((catalogo["pan"], 100), (catalogo["medialuna"], 50)):
        assert admin.put(f"{API}/productos/{pid}/stock", json={"stock_mostrador": n}).status_code == 200
    cliente = admin.post(f"{API}/clientes", json={"nombre": "Bar del Puerto"}).json()

    def punto(nombre, coord, **extra):
        r = admin.post(
            f"{API}/contabilidad/puntos-entrega",
            json={"cliente_id": cliente["id"], "nombre": nombre, "latitud": coord[0],
                  "longitud": coord[1], **extra},
        )
        assert r.status_code == 201, r.text
        return r.json()

    return {
        "admin": admin, "repa": repa, "cliente": cliente, "pan": catalogo["pan"],
        "medialuna": catalogo["medialuna"],
        "repartidor_id": admin.get(f"{API}/entregas/repartidores").json()[0]["id"],
        "centro": punto("Centro", ("-34.603700", "-58.381600")),
        "norte": punto("Norte", ("-34.580000", "-58.420000")),
        "punto": punto,
    }
