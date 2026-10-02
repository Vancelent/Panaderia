"""Ruta sugerida y utilidades geográficas. Funciones puras, sin base de datos ni servicios pagos.

Las distancias son en línea recta (fórmula de haversine): alcanza para ordenar una ruta y no
contempla calles de una mano. No es dinero, así que acá se usa `float`; los resultados se
guardan redondeados en columnas Numeric.

Orden sugerido (docs/rfc-001 §5.1):
1. Los puntos que cierran antes se visitan primero: se agrupan por franjas de 60 minutos según la
   hora hasta la que reciben (los que no tienen horario, al final).
2. Dentro de cada franja se minimiza la distancia: vecino más cercano y después mejora 2-opt.
3. Los puntos sin coordenadas no se pueden ubicar: van al final, en el orden en que vinieron.
"""

import math
from dataclasses import dataclass
from datetime import time

RADIO_TIERRA_KM = 6371.0088
FRANJA_MINUTOS = 60
SIN_HORARIO = 10**6  # franja que ordena después de cualquier horario real


@dataclass(frozen=True)
class Parada:
    id: int
    latitud: float | None = None
    longitud: float | None = None
    cierre: time | None = None  # hora hasta la que recibe

    @property
    def ubicada(self) -> bool:
        return self.latitud is not None and self.longitud is not None


Coord = tuple[float, float]


def haversine_km(a: Coord, b: Coord) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * RADIO_TIERRA_KM * math.asin(min(1.0, math.sqrt(h)))


def distancia_m(a: Coord, b: Coord) -> float:
    return haversine_km(a, b) * 1000


def _coord(p: Parada) -> Coord:
    return (p.latitud, p.longitud)


def _franja(p: Parada) -> int:
    if p.cierre is None:
        return SIN_HORARIO
    return (p.cierre.hour * 60 + p.cierre.minute) // FRANJA_MINUTOS


def _vecino_mas_cercano(inicio: Coord, pendientes: list[Parada]) -> list[Parada]:
    restantes = list(pendientes)
    orden, actual = [], inicio
    while restantes:
        siguiente = min(restantes, key=lambda p: (haversine_km(actual, _coord(p)), p.id))
        restantes.remove(siguiente)
        orden.append(siguiente)
        actual = _coord(siguiente)
    return orden


def _largo(inicio: Coord, orden: list[Parada]) -> float:
    total, actual = 0.0, inicio
    for p in orden:
        total += haversine_km(actual, _coord(p))
        actual = _coord(p)
    return total


def _dos_opt(inicio: Coord, orden: list[Parada], max_pasadas: int = 50) -> list[Parada]:
    """Mejora un camino abierto con el inicio fijo invirtiendo tramos mientras acorte la distancia."""
    orden = list(orden)
    n = len(orden)
    for _ in range(max_pasadas):
        mejoro = False
        for i in range(n - 1):
            for j in range(i + 1, n):
                anterior = inicio if i == 0 else _coord(orden[i - 1])
                posterior = _coord(orden[j + 1]) if j + 1 < n else None
                antes = haversine_km(anterior, _coord(orden[i]))
                despues = haversine_km(anterior, _coord(orden[j]))
                if posterior is not None:
                    antes += haversine_km(_coord(orden[j]), posterior)
                    despues += haversine_km(_coord(orden[i]), posterior)
                if despues + 1e-9 < antes:
                    orden[i : j + 1] = reversed(orden[i : j + 1])
                    mejoro = True
        if not mejoro:
            break
    return orden


def ordenar_ruta(paradas: list[Parada], origen: Coord | None = None) -> tuple[list[int], float]:
    """Devuelve (ids en el orden sugerido, distancia total en km desde el origen).

    Sin `origen` se parte del centro de los puntos ubicados. Es determinista: mismos datos,
    mismo orden.
    """
    ubicadas = [p for p in paradas if p.ubicada]
    sin_ubicar = [p for p in paradas if not p.ubicada]
    if not ubicadas:
        return [p.id for p in paradas], 0.0

    if origen is None:
        origen = (
            sum(p.latitud for p in ubicadas) / len(ubicadas),
            sum(p.longitud for p in ubicadas) / len(ubicadas),
        )

    franjas: dict[int, list[Parada]] = {}
    for p in ubicadas:
        franjas.setdefault(_franja(p), []).append(p)

    orden: list[Parada] = []
    actual = origen
    for clave in sorted(franjas):
        tramo = _vecino_mas_cercano(actual, franjas[clave])
        tramo = _dos_opt(actual, tramo)
        orden.extend(tramo)
        actual = _coord(tramo[-1])

    ids = [p.id for p in orden] + [p.id for p in sin_ubicar]
    return ids, _largo(origen, orden)


# ---------- Traza GPS ----------


def distancia_traza_km(puntos: list[Coord]) -> float:
    return sum(haversine_km(a, b) for a, b in zip(puntos, puntos[1:], strict=False))


def _a_metros(puntos: list[Coord]) -> list[Coord]:
    """Proyección plana local (suficiente para simplificar tramos de una ciudad)."""
    lat0 = sum(p[0] for p in puntos) / len(puntos)
    k = math.cos(math.radians(lat0))
    return [((lon) * k * 111_320.0, lat * 110_540.0) for lat, lon in puntos]


def _dist_a_segmento(p: Coord, a: Coord, b: Coord) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx == dy == 0:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def simplificar_traza(puntos: list[Coord], tolerancia_m: float = 15.0) -> list[int]:
    """Douglas-Peucker: índices de los puntos que conservan la forma del recorrido.

    Sirve para no mandar miles de puntos al mapa. Es iterativo (sin recursión) y siempre
    conserva el primero y el último.
    """
    n = len(puntos)
    if n <= 2:
        return list(range(n))
    plano = _a_metros(puntos)
    conservar = [False] * n
    conservar[0] = conservar[-1] = True
    pila = [(0, n - 1)]
    while pila:
        i, j = pila.pop()
        mayor, indice = 0.0, -1
        for k in range(i + 1, j):
            d = _dist_a_segmento(plano[k], plano[i], plano[j])
            if d > mayor:
                mayor, indice = d, k
        if indice != -1 and mayor > tolerancia_m:
            conservar[indice] = True
            pila.extend([(i, indice), (indice, j)])
    return [i for i, c in enumerate(conservar) if c]
