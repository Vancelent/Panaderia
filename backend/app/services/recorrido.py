"""Traza GPS del reparto: guardado idempotente, datos para el mapa del dueño y retención.

La traza es una tabla de solo agregado: insertar puntos no toma bloqueos sobre filas compartidas,
así que no interfiere con la caja ni con las entregas (docs/rfc-001 §1.3). En PostgreSQL la tabla
está particionada por mes y la retención de 90 días se resuelve eliminando particiones enteras
(§5.4): es instantáneo y no deja filas muertas para el autovacuum.
"""

import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import utcnow
from app.db.utils import insertar_nuevos
from app.models import (
    EstadoEntregaEnum,
    HojaRuta,
    OperacionIdempotente,
    RecorridoEvento,
    RecorridoPunto,
)
from app.schemas.entregas import RecorridoLoteIn
from app.services import rutas

DOS_DECIMALES = Decimal("0.01")
MAX_PUNTOS_MAPA = 20_000
TERMINALES = (EstadoEntregaEnum.ENTREGADA, EstadoEntregaEnum.PARCIAL, EstadoEntregaEnum.NO_ENTREGADA)


# ---------- Guardado ----------


def guardar_lote(db: Session, hoja_id: int, lote: RecorridoLoteIn, *, commit: bool = True) -> dict:
    """Guarda un lote de puntos y cortes. Reenviarlo (mismo lote_id) no duplica nada."""
    ahora = utcnow()
    nuevos = 0
    if lote.puntos:
        filas = [
            {
                "lote_id": lote.lote_id,
                "registrado_en_dispositivo": p.registrado_en,
                "hoja_id": hoja_id,
                "latitud": p.latitud,
                "longitud": p.longitud,
                "precision_m": p.precision_m,
                "recibido_en_servidor": ahora,
            }
            for p in lote.puntos
        ]
        nuevos = insertar_nuevos(db, RecorridoPunto.__table__, filas)

    eventos_nuevos = 0
    for ev in lote.eventos:
        insertado = insertar_nuevos(
            db, RecorridoEvento.__table__,
            {"hoja_id": hoja_id, "tipo": ev.tipo, "desde": ev.desde, "hasta": ev.hasta,
             "recibido_en_servidor": ahora},
        )
        if insertado:
            eventos_nuevos += 1
        elif ev.hasta is not None:
            # El corte se informó abierto y ahora se informa cuándo terminó
            db.execute(
                update(RecorridoEvento)
                .where(
                    RecorridoEvento.hoja_id == hoja_id,
                    RecorridoEvento.tipo == ev.tipo,
                    RecorridoEvento.desde == ev.desde,
                    RecorridoEvento.hasta.is_(None),
                )
                .values(hasta=ev.hasta)
            )
    if commit:
        db.commit()
    return {"recibidos": len(lote.puntos), "nuevos": nuevos, "eventos_nuevos": eventos_nuevos}


# ---------- Lectura ----------


def _puntos_ordenados(db: Session, hoja_id: int):
    return db.execute(
        select(
            RecorridoPunto.latitud, RecorridoPunto.longitud, RecorridoPunto.registrado_en_dispositivo
        )
        .where(RecorridoPunto.hoja_id == hoja_id)
        .order_by(RecorridoPunto.registrado_en_dispositivo)
        .limit(MAX_PUNTOS_MAPA)
    ).all()


def distancia_real_km(db: Session, hoja_id: int) -> Decimal | None:
    puntos = [(float(la), float(lo)) for la, lo, _ in _puntos_ordenados(db, hoja_id)]
    if len(puntos) < 2:
        return None
    return Decimal(str(rutas.distancia_traza_km(puntos))).quantize(DOS_DECIMALES)


def _fuera_de_orden(entregas) -> int:
    """Entregas atendidas en un orden distinto al sugerido (comparando solo las atendidas)."""
    atendidas = [e for e in entregas if e.orden_real is not None]
    por_sugerido = {e.id: i + 1 for i, e in enumerate(sorted(atendidas, key=lambda e: e.orden_sugerido))}
    return sum(1 for e in atendidas if por_sugerido[e.id] != e.orden_real)


def obtener_recorrido(db: Session, hoja: HojaRuta) -> dict:
    """Todo lo que necesita el mapa: ruta sugerida, traza real, entregas e indicadores."""
    settings = get_settings()
    umbral = settings.alerta_distancia_entrega_m
    puntos = _puntos_ordenados(db, hoja.id)
    coords = [(float(la), float(lo)) for la, lo, _ in puntos]
    conservados = rutas.simplificar_traza(coords) if coords else []
    traza = [
        {"latitud": puntos[i][0], "longitud": puntos[i][1], "registrado_en": puntos[i][2]}
        for i in conservados
    ]

    sugerida, entregas_mapa, lejos = [], [], 0
    for e in sorted(hoja.entregas, key=lambda e: e.orden_sugerido):
        p = e.punto
        if p.latitud is not None and p.longitud is not None:
            sugerida.append({
                "entrega_id": e.id, "orden_sugerido": e.orden_sugerido, "nombre": p.nombre,
                "latitud": p.latitud, "longitud": p.longitud,
            })
        distancia = None
        if e.latitud is not None and p.latitud is not None:
            distancia = round(
                rutas.distancia_m(
                    (float(e.latitud), float(e.longitud)), (float(p.latitud), float(p.longitud))
                )
            )
        es_lejos = distancia is not None and distancia > umbral and e.estado in TERMINALES
        lejos += es_lejos
        entregas_mapa.append({
            "entrega_id": e.id, "punto_nombre": p.nombre, "estado": e.estado,
            "orden_sugerido": e.orden_sugerido, "orden_real": e.orden_real,
            "latitud": e.latitud, "longitud": e.longitud,
            "punto_latitud": p.latitud, "punto_longitud": p.longitud,
            "hora": e.confirmada_en_dispositivo or e.recibida_en_servidor,
            "distancia_al_punto_m": distancia, "lejos": es_lejos,
        })

    eventos = [
        {"tipo": ev.tipo, "desde": ev.desde, "hasta": ev.hasta}
        for ev in db.scalars(
            select(RecorridoEvento).where(RecorridoEvento.hoja_id == hoja.id).order_by(RecorridoEvento.desde)
        )
    ]

    real = hoja.distancia_real_km
    if real is None and len(coords) >= 2:
        real = Decimal(str(rutas.distancia_traza_km(coords))).quantize(DOS_DECIMALES)
    fin = hoja.rendida_en or (puntos[-1][2] if puntos else None)
    duracion = None
    if hoja.iniciada_en and fin:
        duracion = max(0, round((fin - hoja.iniciada_en).total_seconds() / 60))

    origen = None
    if settings.panaderia_latitud is not None and settings.panaderia_longitud is not None:
        origen = {"latitud": settings.panaderia_latitud, "longitud": settings.panaderia_longitud}

    return {
        "hoja_id": hoja.id, "estado": hoja.estado, "origen": origen, "sugerida": sugerida,
        "traza": traza, "puntos_totales": len(puntos), "entregas": entregas_mapa, "eventos": eventos,
        "indicadores": {
            "distancia_sugerida_km": hoja.distancia_sugerida_km, "distancia_real_km": real,
            "duracion_min": duracion, "entregas_fuera_de_orden": _fuera_de_orden(hoja.entregas),
            "entregas_lejos": lejos, "tramos_sin_traza": len(eventos),
        },
    }


# ---------- Retención: particiones mensuales ----------

_PARTICION = re.compile(r"^recorrido_puntos_(\d{4})_(\d{2})$")


def _mes_siguiente(d: date) -> date:
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def nombre_particion(inicio: date) -> str:
    return f"recorrido_puntos_{inicio:%Y_%m}"


def _limite(d: date) -> str:
    # Siempre en UTC: sin esto el límite dependería de la zona horaria de la sesión
    return f"'{d.isoformat()} 00:00:00+00'"


def asegurar_particion(db: Session, mes: date) -> bool:
    """Crea la partición del mes si no existe. Devuelve True si la creó.

    Si la partición DEFAULT ya tiene puntos de ese mes (llegaron antes de que existiera la
    partición), se mueven: PostgreSQL no permite crear una partición que los contenga.
    """
    inicio = mes.replace(day=1)
    fin = _mes_siguiente(inicio)
    nombre = nombre_particion(inicio)
    if db.scalar(text("SELECT to_regclass(:n)"), {"n": nombre}) is not None:
        return False

    rango = (
        "registrado_en_dispositivo >= " + _limite(inicio) + " AND registrado_en_dispositivo < " + _limite(fin)
    )
    # Todo se arma con fechas y un nombre generados acá (nunca con datos del usuario)
    en_default = f"FROM recorrido_puntos_default WHERE {rango}"  # noqa: S608
    hay = db.scalar(text(f"SELECT count(*) {en_default}"))
    if hay:
        db.execute(text(f"CREATE TEMP TABLE _reubicar ON COMMIT DROP AS SELECT * {en_default}"))
        db.execute(text(f"DELETE {en_default}"))
    crear = (
        f"CREATE TABLE {nombre} PARTITION OF recorrido_puntos "  # noqa: S608
        f"FOR VALUES FROM ({_limite(inicio)}) TO ({_limite(fin)})"
    )
    db.execute(text(crear))
    if hay:
        db.execute(text("INSERT INTO recorrido_puntos SELECT * FROM _reubicar"))
    return True


def _particiones(db: Session) -> list[str]:
    return list(
        db.scalars(
            text(
                "SELECT c.relname FROM pg_inherits i "
                "JOIN pg_class c ON c.oid = i.inhrelid "
                "JOIN pg_class p ON p.oid = i.inhparent "
                "WHERE p.relname = 'recorrido_puntos'"
            )
        )
    )


def _eliminar_particiones_vencidas(db: Session, corte: datetime) -> list[str]:
    """Elimina las particiones cuyo mes termina antes del corte (todo su contenido está vencido)."""
    eliminadas = []
    for nombre in sorted(_particiones(db)):
        m = _PARTICION.match(nombre)
        if not m:
            continue
        fin = _mes_siguiente(date(int(m.group(1)), int(m.group(2)), 1))
        if datetime(fin.year, fin.month, fin.day, tzinfo=UTC) <= corte:
            db.execute(text(f"DROP TABLE {nombre}"))  # noqa: S608  (el nombre salió de la regex)
            eliminadas.append(nombre)
    return eliminadas


def mantenimiento(db: Session, ahora: datetime | None = None) -> dict:
    """Tarea diaria (`python -m app.cli mantenimiento-gps`).

    - Crea la partición del mes en curso y la del siguiente (si faltan).
    - Elimina las particiones de más de `RETENCION_GPS_DIAS` días.
    - Borra los puntos vencidos del mes "borde" (que tiene días de más y de menos).
    - Borra cortes de traza y operaciones idempotentes vencidos.

    No toca el resumen de cada hoja (distancia real, orden real, posición de cada entrega).
    """
    ahora = ahora or utcnow()
    if ahora.tzinfo is None:
        ahora = ahora.replace(tzinfo=UTC)
    corte = ahora - timedelta(days=get_settings().retencion_gps_dias)
    resultado: dict = {"particiones_creadas": [], "particiones_eliminadas": [], "corte": corte}

    if db.get_bind().dialect.name == "postgresql":
        hoy = ahora.astimezone(UTC).date().replace(day=1)
        for mes in (hoy, _mes_siguiente(hoy)):
            if asegurar_particion(db, mes):
                resultado["particiones_creadas"].append(nombre_particion(mes))
        resultado["particiones_eliminadas"] = _eliminar_particiones_vencidas(db, corte)

    resultado["puntos_borrados"] = db.execute(
        delete(RecorridoPunto).where(RecorridoPunto.registrado_en_dispositivo < corte)
    ).rowcount
    resultado["eventos_borrados"] = db.execute(
        delete(RecorridoEvento).where(RecorridoEvento.recibido_en_servidor < corte)
    ).rowcount
    resultado["operaciones_borradas"] = db.execute(
        delete(OperacionIdempotente).where(OperacionIdempotente.creado_en < corte)
    ).rowcount
    db.commit()
    return resultado


def contar_puntos(db: Session, hoja_id: int) -> int:
    return db.scalar(
        select(func.count()).select_from(RecorridoPunto).where(RecorridoPunto.hoja_id == hoja_id)
    )
