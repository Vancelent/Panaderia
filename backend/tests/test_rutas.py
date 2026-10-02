"""Ruta sugerida (vecino más cercano + 2-opt) y simplificación de la traza. Funciones puras."""

from datetime import time

import pytest

from app.services import rutas
from app.services.rutas import Parada

ORIGEN = (-34.6000, -58.4000)


def _p(id, lat, lon, cierre=None):
    return Parada(id=id, latitud=lat, longitud=lon, cierre=cierre)


def test_haversine_de_un_grado_de_latitud():
    km = rutas.haversine_km((0.0, 0.0), (1.0, 0.0))
    assert km == pytest.approx(111.19, abs=0.05)
    assert rutas.haversine_km((10.0, 20.0), (10.0, 20.0)) == 0
    assert rutas.distancia_m((0.0, 0.0), (0.0, 0.001)) == pytest.approx(111.19, abs=0.1)


def test_sin_paradas_o_sin_ubicacion_no_falla():
    assert rutas.ordenar_ruta([], ORIGEN) == ([], 0.0)
    ids, km = rutas.ordenar_ruta([_p(1, None, None), _p(2, None, None)], ORIGEN)
    assert ids == [1, 2] and km == 0.0


def test_una_parada():
    ids, km = rutas.ordenar_ruta([_p(7, -34.61, -58.40)], ORIGEN)
    assert ids == [7] and km == pytest.approx(rutas.haversine_km(ORIGEN, (-34.61, -58.40)))


def test_vecino_mas_cercano_sobre_una_linea():
    # Puntos sobre un meridiano, desordenados: el recorrido es de menor a mayor distancia
    paradas = [_p(3, -34.63, -58.40), _p(1, -34.61, -58.40), _p(2, -34.62, -58.40)]
    ids, km = rutas.ordenar_ruta(paradas, ORIGEN)
    assert ids == [1, 2, 3]
    assert km == pytest.approx(rutas.haversine_km(ORIGEN, (-34.63, -58.40)), rel=1e-6)


def test_los_horarios_mas_tempranos_van_primero():
    # El 2 está más lejos pero cierra antes: se visita antes que el 1 (que cierra a las 11)
    paradas = [
        _p(1, -34.601, -58.40, cierre=time(11, 0)),
        _p(2, -34.650, -58.40, cierre=time(8, 30)),
        _p(3, -34.602, -58.40, cierre=time(12, 30)),
    ]
    ids, _ = rutas.ordenar_ruta(paradas, ORIGEN)
    assert ids[0] == 2
    assert ids[1:] == [1, 3]


def test_sin_horario_va_despues_de_los_que_tienen():
    paradas = [_p(1, -34.601, -58.40), _p(2, -34.700, -58.40, cierre=time(9, 0))]
    ids, _ = rutas.ordenar_ruta(paradas, ORIGEN)
    assert ids == [2, 1]


def test_los_puntos_sin_ubicacion_van_al_final_en_su_orden():
    paradas = [_p(5, None, None), _p(1, -34.61, -58.40), _p(6, None, None), _p(2, -34.62, -58.40)]
    ids, _ = rutas.ordenar_ruta(paradas, ORIGEN)
    assert ids == [1, 2, 5, 6]


def test_dos_opt_no_empeora_y_deshace_cruces():
    # Cuatro esquinas de un cuadrado visitadas en cruz: el 2-opt las ordena sin cruzar
    esquinas = [(-34.60, -58.40), (-34.60, -58.39), (-34.61, -58.39), (-34.61, -58.40)]
    paradas = [_p(i, *c) for i, c in enumerate(esquinas)]
    cruzado = [paradas[0], paradas[2], paradas[1], paradas[3]]
    origen = (-34.599, -58.401)
    mejor = rutas._dos_opt(origen, cruzado)
    assert rutas._largo(origen, mejor) <= rutas._largo(origen, cruzado)
    assert rutas._largo(origen, mejor) < rutas._largo(origen, cruzado)


def test_es_determinista():
    paradas = [_p(i, -34.60 - (i % 5) * 0.003, -58.40 + (i % 3) * 0.004) for i in range(1, 25)]
    a = rutas.ordenar_ruta(paradas, ORIGEN)
    b = rutas.ordenar_ruta(list(reversed(paradas)), ORIGEN)
    assert a == b


def test_sin_origen_parte_del_centro():
    paradas = [_p(1, -34.60, -58.40), _p(2, -34.62, -58.40)]
    ids, km = rutas.ordenar_ruta(paradas)
    assert sorted(ids) == [1, 2] and km > 0


def test_cincuenta_paradas_en_milisegundos():
    import time as t

    paradas = [_p(i, -34.55 - (i * 7 % 40) * 0.002, -58.45 + (i * 11 % 40) * 0.002) for i in range(60)]
    t0 = t.perf_counter()
    ids, _ = rutas.ordenar_ruta(paradas, ORIGEN)
    assert sorted(ids) == list(range(60))
    assert t.perf_counter() - t0 < 2


# ---------- Traza ----------


def test_distancia_de_la_traza():
    assert rutas.distancia_traza_km([]) == 0
    assert rutas.distancia_traza_km([(0.0, 0.0)]) == 0
    assert rutas.distancia_traza_km([(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]) == pytest.approx(222.39, abs=0.1)


def test_simplificar_una_linea_recta_deja_los_extremos():
    puntos = [(-34.60 - i * 0.0005, -58.40) for i in range(40)]
    assert rutas.simplificar_traza(puntos) == [0, 39]


def test_simplificar_conserva_las_esquinas():
    # Camina 1 km al sur y después 1 km al este: la esquina tiene que sobrevivir
    sur = [(-34.60 - i * 0.001, -58.40) for i in range(10)]
    este = [(-34.609, -58.40 + i * 0.0011) for i in range(1, 10)]
    puntos = sur + este
    conservados = rutas.simplificar_traza(puntos)
    assert conservados[0] == 0 and conservados[-1] == len(puntos) - 1
    assert 9 in conservados  # la esquina
    assert len(conservados) < len(puntos)


def test_simplificar_casos_chicos():
    assert rutas.simplificar_traza([]) == []
    assert rutas.simplificar_traza([(1.0, 1.0)]) == [0]
    assert rutas.simplificar_traza([(1.0, 1.0), (2.0, 2.0)]) == [0, 1]


def test_simplificar_no_recursa_con_trazas_largas():
    # Un zigzag de 20.000 puntos no debe agotar la pila (el algoritmo es iterativo)
    puntos = [(-34.60 + (i % 2) * 0.001, -58.40 + i * 0.0001) for i in range(20_000)]
    conservados = rutas.simplificar_traza(puntos, tolerancia_m=5)
    assert conservados[0] == 0 and conservados[-1] == 19_999
