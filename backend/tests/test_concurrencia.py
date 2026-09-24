import os
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.models import RolEnum
from tests.conftest import login

API = "/api/v1"

pytestmark = pytest.mark.skipif(
    not os.environ["DATABASE_URL"].startswith("postgresql"),
    reason="El bloqueo de filas (FOR UPDATE) solo se puede probar en Postgres",
)


def test_ventas_concurrentes_no_sobrevenden(como, catalogo):
    # 3 cajeras con turno abierto compiten por las 5 medialunas
    cajas = []
    for i in range(3):
        como(RolEnum.VENDEDORA, f"caja{i}")
        c = login(f"caja{i}")
        c.post(f"{API}/turnos", json={"efectivo_inicial": 0})
        cajas.append(c)

    def vender(n):
        c = cajas[n % len(cajas)]
        r = c.post(f"{API}/ventas", json={"items": [{"producto_id": catalogo["medialuna"], "cantidad": 1}]})
        return r.status_code

    with ThreadPoolExecutor(max_workers=12) as pool:
        resultados = list(pool.map(vender, range(12)))

    assert resultados.count(201) == 5
    assert resultados.count(409) == 7
    stock = {p["id"]: p["stock_mostrador"] for p in cajas[0].get(f"{API}/productos").json()}
    assert stock[catalogo["medialuna"]] == 0
