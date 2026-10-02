"""Retención de la traza GPS (docs/rfc-001 §5.4): particiones mensuales y borrado de lo vencido.

Los tests de particiones solo corren contra PostgreSQL; en SQLite la tabla es normal y solo se
prueba el borrado de lo vencido.
"""

import os
import subprocess
import sys
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select, text

from app.core.config import Settings
from app.db.session import SessionLocal
from app.models import (
    Entrega,
    HojaRuta,
    OperacionIdempotente,
    RecorridoEvento,
    RecorridoPunto,
    RolEnum,
    TipoEventoRecorridoEnum,
)
from app.services import recorrido
from tests.conftest import crear_usuario
from tests.test_entregas import ENT, _en_ruta, _entregar, _hoja

POSTGRES = os.environ["DATABASE_URL"].startswith("postgresql")
solo_postgres = pytest.mark.skipif(not POSTGRES, reason="El particionado solo existe en PostgreSQL")
BACKEND = Path(__file__).resolve().parents[1]


def utc(y, m, d, h=12):
    return datetime(y, m, d, h, tzinfo=UTC)


@pytest.fixture
def limpiar_particiones():
    yield
    if POSTGRES:
        with SessionLocal() as s:
            for nombre in recorrido._particiones(s):
                if nombre != "recorrido_puntos_default":
                    s.execute(text(f"DROP TABLE {nombre}"))
            s.commit()


@pytest.fixture
def hoja_id(reparto):
    return _hoja(reparto, (reparto["centro"], {reparto["pan"]: 1}))["id"]


def _agregar_puntos(hoja_id, fechas):
    with SessionLocal() as s:
        for f in fechas:
            s.add(RecorridoPunto(
                lote_id=uuid.uuid4(), registrado_en_dispositivo=f, hoja_id=hoja_id,
                latitud=Decimal("-34.6"), longitud=Decimal("-58.4"),
            ))
        s.commit()


def _contar(tabla="recorrido_puntos"):
    with SessionLocal() as s:
        return s.scalar(text(f"SELECT count(*) FROM {tabla}"))  # noqa: S608


def _particiones():
    with SessionLocal() as s:
        return sorted(recorrido._particiones(s))


# ---------- Configuración ----------


def test_las_coordenadas_vacias_del_env_example_no_rompen_la_configuracion():
    s = Settings(
        database_url="sqlite:///x.db", jwt_secret="x" * 40, panaderia_latitud="", panaderia_longitud=" ",
    )
    assert s.panaderia_latitud is None and s.panaderia_longitud is None
    s = Settings(database_url="sqlite:///x.db", jwt_secret="x" * 40, panaderia_latitud="-34.6037",
                 panaderia_longitud="-58.3816")
    assert s.panaderia_latitud == Decimal("-34.6037")
    assert s.retencion_gps_dias == 90 and s.alerta_distancia_entrega_m == 300


# ---------- Borrado de lo vencido (cualquier motor) ----------


def test_el_mantenimiento_borra_lo_vencido_y_conserva_lo_reciente(hoja_id, limpiar_particiones):
    ahora = utc(2026, 6, 30)
    _agregar_puntos(hoja_id, [ahora - timedelta(days=100), ahora - timedelta(days=91),
                              ahora - timedelta(days=89), ahora - timedelta(days=1)])
    with SessionLocal() as s:
        s.add_all([
            RecorridoEvento(hoja_id=hoja_id, tipo=TipoEventoRecorridoEnum.GPS_SIN_SENAL,
                            desde=ahora - timedelta(days=95), recibido_en_servidor=ahora - timedelta(days=95)),
            RecorridoEvento(hoja_id=hoja_id, tipo=TipoEventoRecorridoEnum.GPS_SIN_SENAL,
                            desde=ahora - timedelta(days=2), recibido_en_servidor=ahora - timedelta(days=2)),
            OperacionIdempotente(operacion_id=uuid.uuid4(), usuario_id=_uid(), tipo="check_in:1",
                                 creado_en=ahora - timedelta(days=120)),
            OperacionIdempotente(operacion_id=uuid.uuid4(), usuario_id=_uid(), tipo="check_in:2",
                                 creado_en=ahora - timedelta(days=3)),
        ])
        s.commit()

    with SessionLocal() as s:
        resultado = recorrido.mantenimiento(s, ahora=ahora)
    assert resultado["puntos_borrados"] >= 0  # en Postgres parte se va con las particiones
    assert _contar() == 2
    with SessionLocal() as s:
        quedan = s.scalars(select(RecorridoPunto.registrado_en_dispositivo)).all()
        assert all((ahora - (q if q.tzinfo else q.replace(tzinfo=UTC))).days < 90 for q in quedan)
        assert s.scalar(select(func.count()).select_from(RecorridoEvento)) == 1
        assert s.scalar(select(func.count()).select_from(OperacionIdempotente)) == 1


def _uid():
    from app.models import Usuario

    with SessionLocal() as s:
        u = s.scalar(select(Usuario.id).where(Usuario.rol == RolEnum.REPARTIDOR))
        return u or crear_usuario("tmp", RolEnum.REPARTIDOR).id


def test_el_mantenimiento_conserva_el_resumen_de_la_hoja(reparto, limpiar_particiones):
    r, pan = reparto, reparto["pan"]
    hoja = _en_ruta(r, (r["centro"], {pan: 2}))
    ahora = datetime.now(UTC)
    _agregar_puntos(hoja["id"], [ahora - timedelta(minutes=5), ahora - timedelta(minutes=4)])
    assert _entregar(r, hoja["entregas"][0]["id"], {pan: 2}).status_code == 200
    rend = r["admin"].post(f"{ENT}/hojas/{hoja['id']}/rendicion", json={"devoluciones": [], "efectivo_declarado": 500})
    assert rend.status_code == 200
    distancia = rend.json()["distancia_real_km"]
    assert _contar() >= 2

    # Pasaron 200 días: toda la traza está vencida
    with SessionLocal() as s:
        recorrido.mantenimiento(s, ahora=ahora + timedelta(days=200))
    assert _contar() == 0

    h = r["admin"].get(f"{ENT}/hojas/{hoja['id']}").json()
    assert h["distancia_real_km"] == distancia
    assert h["estado"] == "Rendida"
    e = h["entregas"][0]
    assert (e["orden_real"], e["estado"]) == (1, "Entregada")
    with SessionLocal() as s:
        entrega = s.get(Entrega, e["id"])
        assert entrega.latitud is not None and entrega.confirmada_en_dispositivo is not None
        assert s.get(HojaRuta, hoja["id"]).distancia_real_km is not None
    # Sin traza, el mapa sigue mostrando la ruta sugerida y las entregas
    mapa = r["admin"].get(f"{ENT}/hojas/{hoja['id']}/recorrido").json()
    assert mapa["puntos_totales"] == 0 and mapa["traza"] == [] and len(mapa["entregas"]) == 1
    assert mapa["indicadores"]["distancia_real_km"] == distancia


# ---------- Particiones (PostgreSQL) ----------


@solo_postgres
def test_crea_la_particion_del_mes_y_la_siguiente(limpiar_particiones):
    with SessionLocal() as s:
        r = recorrido.mantenimiento(s, ahora=utc(2026, 12, 20))
    assert r["particiones_creadas"] == ["recorrido_puntos_2026_12", "recorrido_puntos_2027_01"]
    assert _particiones() == ["recorrido_puntos_2026_12", "recorrido_puntos_2027_01", "recorrido_puntos_default"]
    with SessionLocal() as s:  # es idempotente
        assert recorrido.mantenimiento(s, ahora=utc(2026, 12, 21))["particiones_creadas"] == []
    # Y los puntos de cada mes caen en su partición
    with SessionLocal() as s:
        assert recorrido.asegurar_particion(s, date(2026, 12, 1)) is False


@solo_postgres
def test_los_limites_de_la_particion_son_utc(hoja_id, limpiar_particiones):
    with SessionLocal() as s:
        recorrido.mantenimiento(s, ahora=utc(2026, 3, 10))
    # 23:59 UTC del 31/03 es marzo; 00:00 UTC del 01/04 es abril (aunque en Buenos Aires aún sea 31/03)
    _agregar_puntos(hoja_id, [datetime(2026, 3, 31, 23, 59, tzinfo=UTC), datetime(2026, 4, 1, 0, 0, tzinfo=UTC)])
    assert _contar("recorrido_puntos_2026_03") == 1
    assert _contar("recorrido_puntos_2026_04") == 1
    assert _contar("recorrido_puntos_default") == 0


@solo_postgres
def test_elimina_las_particiones_vencidas_sin_tocar_las_vigentes(hoja_id, limpiar_particiones):
    with SessionLocal() as s:
        for mes in (1, 2, 3, 4, 5):
            recorrido.asegurar_particion(s, date(2026, mes, 1))
        s.commit()
    fechas = [utc(2026, 1, 10), utc(2026, 1, 25), utc(2026, 2, 5), utc(2026, 2, 25), utc(2026, 4, 30), utc(2026, 5, 18)]
    _agregar_puntos(hoja_id, fechas)
    assert _contar() == 6

    # Hoy es el 20/05: el corte es el 19/02 (90 días). Enero ya terminó antes del corte: se descarta
    # entera. Febrero es el mes "borde": se queda, pero sin los puntos anteriores al corte.
    with SessionLocal() as s:
        r = recorrido.mantenimiento(s, ahora=utc(2026, 5, 20))
    assert r["particiones_eliminadas"] == ["recorrido_puntos_2026_01"]
    assert "recorrido_puntos_2026_01" not in _particiones()
    assert _contar("recorrido_puntos_2026_02") == 1   # solo el del 25/02
    assert _contar("recorrido_puntos_2026_04") == 1
    assert _contar("recorrido_puntos_2026_05") == 1
    assert r["puntos_borrados"] == 1                   # el del 05/02 (borde)
    assert _contar() == 3


@solo_postgres
def test_los_puntos_con_fecha_fuera_de_rango_no_se_pierden(hoja_id, limpiar_particiones):
    _agregar_puntos(hoja_id, [utc(2031, 7, 1)])  # reloj desfasado: no hay partición para ese mes
    assert _contar("recorrido_puntos_default") == 1
    with SessionLocal() as s:
        assert s.scalar(select(func.count()).select_from(RecorridoPunto)) == 1


@solo_postgres
def test_al_crear_la_particion_se_reubican_los_puntos_que_ya_estaban_en_default(hoja_id, limpiar_particiones):
    _agregar_puntos(hoja_id, [utc(2026, 8, 3), utc(2026, 8, 20), utc(2026, 9, 2)])
    assert _contar("recorrido_puntos_default") == 3
    with SessionLocal() as s:
        assert recorrido.asegurar_particion(s, date(2026, 8, 1)) is True
        s.commit()
    assert _contar("recorrido_puntos_2026_08") == 2
    assert _contar("recorrido_puntos_default") == 1  # el de septiembre sigue esperando su partición
    assert _contar() == 3


@solo_postgres
def test_los_lotes_repetidos_se_ignoran_tambien_en_la_tabla_particionada(reparto, limpiar_particiones):
    r, pan = reparto, reparto["pan"]
    hoja = _en_ruta(r, (r["centro"], {pan: 1}))
    with SessionLocal() as s:
        recorrido.mantenimiento(s)  # particiones del mes en curso y el siguiente
    lote = {"lote_id": str(uuid.uuid4()), "puntos": [
        {"latitud": "-34.6", "longitud": "-58.4", "registrado_en": (datetime.now(UTC) - timedelta(minutes=m)).isoformat()}
        for m in (3, 2, 1)
    ]}
    url = f"{ENT}/hojas/{hoja['id']}/recorrido"
    assert r["repa"].post(url, json=lote).json()["nuevos"] == 3
    assert r["repa"].post(url, json=lote).json()["nuevos"] == 0
    assert _contar() == 4  # + el punto de salida


@solo_postgres
def test_el_comando_de_mantenimiento(hoja_id, limpiar_particiones):
    _agregar_puntos(hoja_id, [datetime.now(UTC) - timedelta(days=400)])
    env = {**os.environ}
    r = subprocess.run([sys.executable, "-m", "app.cli", "mantenimiento-gps"], cwd=BACKEND, env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-1500:]
    assert "Mantenimiento GPS" in r.stdout and "puntos borrados: 1" in r.stdout
    assert _contar() == 0
    mes = datetime.now(UTC).strftime("%Y_%m")
    assert f"recorrido_puntos_{mes}" in _particiones()
    # Es repetible: la segunda vez no crea ni borra nada
    r = subprocess.run([sys.executable, "-m", "app.cli", "mantenimiento-gps"], cwd=BACKEND, env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0 and "creadas: ninguna" in r.stdout and "puntos borrados: 0" in r.stdout


def test_el_comando_existe_y_no_pisa_a_crear_admin():
    r = subprocess.run([sys.executable, "-m", "app.cli", "--help"], cwd=BACKEND, capture_output=True, text=True,
                       env={**os.environ})
    assert r.returncode == 0
    assert "mantenimiento-gps" in r.stdout and "crear-admin" in r.stdout
