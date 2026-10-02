"""Hojas de ruta, entregas y recorrido GPS (docs/rfc-001 §3 y §5)."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow
from app.models.contabilidad import PuntoEntrega
from app.models.enums import (
    EstadoEntregaEnum,
    EstadoHojaRutaEnum,
    TipoEventoEntregaEnum,
    TipoEventoRecorridoEnum,
)
from app.models.inventario import Producto
from app.models.usuario import Usuario

Coordenada = Numeric(9, 6)
Distancia = Numeric(7, 2)


class HojaRuta(Base):
    __tablename__ = "hojas_ruta"

    id: Mapped[int] = mapped_column(primary_key=True)
    fecha: Mapped[date] = mapped_column(index=True)
    repartidor_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    # Turno de REPARTO que abre la carga; ahí caen las ventas y cobros de la ruta
    turno_id: Mapped[int | None] = mapped_column(ForeignKey("turnos.id"))
    estado: Mapped[EstadoHojaRutaEnum] = mapped_column(
        Enum(EstadoHojaRutaEnum), default=EstadoHojaRutaEnum.BORRADOR, index=True
    )
    creado_por_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = mapped_column(default=utcnow)
    confirmada_en: Mapped[datetime | None]
    cargada_en: Mapped[datetime | None]
    iniciada_en: Mapped[datetime | None]
    rendida_en: Mapped[datetime | None]
    distancia_sugerida_km: Mapped[Decimal | None] = mapped_column(Distancia)
    # Resumen permanente: la traza cruda se borra a los 90 días, esto no
    distancia_real_km: Mapped[Decimal | None] = mapped_column(Distancia)

    repartidor: Mapped[Usuario] = relationship(foreign_keys=[repartidor_id])
    items: Mapped[list["HojaRutaItem"]] = relationship(
        back_populates="hoja", cascade="all, delete-orphan", order_by="HojaRutaItem.id"
    )
    entregas: Mapped[list["Entrega"]] = relationship(
        back_populates="hoja", cascade="all, delete-orphan", order_by="(Entrega.orden_sugerido, Entrega.id)"
    )


class HojaRutaItem(Base):
    """Carga del vehículo por producto: reservado al confirmar, cargado al salir, devuelto al rendir."""

    __tablename__ = "hojas_ruta_items"
    __table_args__ = (
        UniqueConstraint("hoja_id", "producto_id"),
        CheckConstraint(
            "cantidad_reservada >= 0 AND cantidad_cargada >= 0 AND cantidad_devuelta >= 0",
            name="ck_hoja_item_cantidades",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    hoja_id: Mapped[int] = mapped_column(ForeignKey("hojas_ruta.id"), index=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"))
    cantidad_reservada: Mapped[int]
    cantidad_cargada: Mapped[int] = mapped_column(default=0)
    cantidad_devuelta: Mapped[int] = mapped_column(default=0)

    hoja: Mapped[HojaRuta] = relationship(back_populates="items")
    producto: Mapped[Producto] = relationship()


class Entrega(Base):
    """Una parada de la hoja. El orden sugerido es solo una sugerencia (D17)."""

    __tablename__ = "entregas"
    __table_args__ = (UniqueConstraint("hoja_id", "punto_entrega_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    hoja_id: Mapped[int] = mapped_column(ForeignKey("hojas_ruta.id"), index=True)
    punto_entrega_id: Mapped[int] = mapped_column(ForeignKey("puntos_entrega.id"))
    orden_sugerido: Mapped[int]
    # Orden en que realmente se atendieron: se asigna al confirmar
    orden_real: Mapped[int | None]
    estado: Mapped[EstadoEntregaEnum] = mapped_column(
        Enum(EstadoEntregaEnum), default=EstadoEntregaEnum.PENDIENTE, index=True
    )
    venta_id: Mapped[int | None] = mapped_column(ForeignKey("ventas.id"))
    numero_remito: Mapped[int | None] = mapped_column(unique=True)
    operacion_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, unique=True)
    latitud: Mapped[Decimal | None] = mapped_column(Coordenada)
    longitud: Mapped[Decimal | None] = mapped_column(Coordenada)
    confirmada_en_dispositivo: Mapped[datetime | None]
    recibida_en_servidor: Mapped[datetime | None]
    recibio_nombre: Mapped[str | None] = mapped_column(String(120))
    motivo_no_entrega: Mapped[str | None] = mapped_column(String(200))

    hoja: Mapped[HojaRuta] = relationship(back_populates="entregas")
    punto: Mapped[PuntoEntrega] = relationship()
    items: Mapped[list["EntregaItem"]] = relationship(
        back_populates="entrega", cascade="all, delete-orphan", order_by="EntregaItem.id"
    )
    eventos: Mapped[list["EntregaEvento"]] = relationship(
        back_populates="entrega", cascade="all, delete-orphan", order_by="EntregaEvento.id"
    )


class EntregaItem(Base):
    __tablename__ = "entregas_items"
    __table_args__ = (
        UniqueConstraint("entrega_id", "producto_id"),
        CheckConstraint(
            "cantidad_planificada > 0 AND cantidad_entregada >= 0", name="ck_entrega_item_cantidades"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    entrega_id: Mapped[int] = mapped_column(ForeignKey("entregas.id"), index=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"))
    cantidad_planificada: Mapped[int]
    cantidad_entregada: Mapped[int] = mapped_column(default=0)
    # Precio de lista, descuento del punto y precio final: congelados al confirmar la hoja
    precio_lista: Mapped[Decimal]
    descuento_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    precio_unitario: Mapped[Decimal]

    entrega: Mapped[Entrega] = relationship(back_populates="items")
    producto: Mapped[Producto] = relationship()


class EntregaEvento(Base):
    """Historial de la entrega, con la posición del dispositivo en cada evento."""

    __tablename__ = "entregas_eventos"

    id: Mapped[int] = mapped_column(primary_key=True)
    entrega_id: Mapped[int] = mapped_column(ForeignKey("entregas.id"), index=True)
    tipo: Mapped[TipoEventoEntregaEnum] = mapped_column(Enum(TipoEventoEntregaEnum))
    latitud: Mapped[Decimal | None] = mapped_column(Coordenada)
    longitud: Mapped[Decimal | None] = mapped_column(Coordenada)
    precision_m: Mapped[Decimal | None] = mapped_column(Numeric(7, 1))
    registrado_en_dispositivo: Mapped[datetime | None]
    recibido_en_servidor: Mapped[datetime] = mapped_column(default=utcnow)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    detalle: Mapped[str | None] = mapped_column(String(200))

    entrega: Mapped[Entrega] = relationship(back_populates="eventos")


class RecorridoPunto(Base):
    """Un punto de la traza GPS real. Tabla de solo agregado, particionada por mes en PostgreSQL.

    La clave natural (lote_id, registrado_en_dispositivo) hace idempotente el reenvío de un
    lote: los puntos repetidos se ignoran (INSERT ... ON CONFLICT DO NOTHING). PostgreSQL exige
    que la clave primaria incluya la de partición, y ninguna otra tabla referencia estas filas.
    """

    __tablename__ = "recorrido_puntos"
    __table_args__ = (
        Index("ix_recorrido_hoja_fecha", "hoja_id", "registrado_en_dispositivo"),
        {"postgresql_partition_by": "RANGE (registrado_en_dispositivo)"},
    )

    lote_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    registrado_en_dispositivo: Mapped[datetime] = mapped_column(primary_key=True)
    hoja_id: Mapped[int] = mapped_column(ForeignKey("hojas_ruta.id"))
    latitud: Mapped[Decimal] = mapped_column(Coordenada)
    longitud: Mapped[Decimal] = mapped_column(Coordenada)
    precision_m: Mapped[Decimal | None] = mapped_column(Numeric(7, 1))
    recibido_en_servidor: Mapped[datetime] = mapped_column(default=utcnow)


class RecorridoEvento(Base):
    """Cortes de la traza: sin señal, permiso revocado o app cerrada. Se muestran como tramos sin traza."""

    __tablename__ = "recorrido_eventos"
    __table_args__ = (UniqueConstraint("hoja_id", "tipo", "desde"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    hoja_id: Mapped[int] = mapped_column(ForeignKey("hojas_ruta.id"), index=True)
    tipo: Mapped[TipoEventoRecorridoEnum] = mapped_column(Enum(TipoEventoRecorridoEnum))
    desde: Mapped[datetime]
    hasta: Mapped[datetime | None]
    recibido_en_servidor: Mapped[datetime] = mapped_column(default=utcnow, index=True)
