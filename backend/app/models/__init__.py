"""Importa todos los modelos para que queden registrados en Base.metadata."""

from app.models.caja import Arqueo, DetalleVenta, Turno, Venta, VentaPago
from app.models.comercial import Cliente, DetallePedido, Pedido
from app.models.compras import CompraMateriaPrima, GastoVario, Proveedor
from app.models.contabilidad import (
    DescuentoPunto,
    MovimientoCuentaCorriente,
    PlantillaEntrega,
    PuntoEntrega,
)
from app.models.enums import (
    DestinoDevolucionEnum,
    EstadoEntregaEnum,
    EstadoHojaRutaEnum,
    EstadoPagoEnum,
    EstadoPedidoEnum,
    EstadoTurnoEnum,
    MetodoPagoEnum,
    OrigenVentaEnum,
    RolEnum,
    TipoEventoEntregaEnum,
    TipoEventoRecorridoEnum,
    TipoMovimientoCtaCteEnum,
    TipoTurnoEnum,
)
from app.models.inventario import (
    ConversionDiaAnterior,
    LoteProduccion,
    MateriaPrima,
    Merma,
    Producto,
    RecetaInsumo,
)
from app.models.reparto import (
    Entrega,
    EntregaEvento,
    EntregaItem,
    HojaRuta,
    HojaRutaItem,
    RecorridoEvento,
    RecorridoPunto,
)
from app.models.soporte import Numerador, OperacionIdempotente
from app.models.usuario import Usuario

__all__ = [
    "Arqueo",
    "Cliente",
    "CompraMateriaPrima",
    "ConversionDiaAnterior",
    "DescuentoPunto",
    "DestinoDevolucionEnum",
    "DetallePedido",
    "DetalleVenta",
    "Entrega",
    "EntregaEvento",
    "EntregaItem",
    "EstadoEntregaEnum",
    "EstadoHojaRutaEnum",
    "EstadoPagoEnum",
    "EstadoPedidoEnum",
    "EstadoTurnoEnum",
    "GastoVario",
    "HojaRuta",
    "HojaRutaItem",
    "LoteProduccion",
    "MateriaPrima",
    "Merma",
    "MetodoPagoEnum",
    "MovimientoCuentaCorriente",
    "Numerador",
    "OperacionIdempotente",
    "OrigenVentaEnum",
    "Pedido",
    "PlantillaEntrega",
    "Producto",
    "Proveedor",
    "PuntoEntrega",
    "RecetaInsumo",
    "RecorridoEvento",
    "RecorridoPunto",
    "RolEnum",
    "TipoEventoEntregaEnum",
    "TipoEventoRecorridoEnum",
    "TipoMovimientoCtaCteEnum",
    "TipoTurnoEnum",
    "Turno",
    "Usuario",
    "Venta",
    "VentaPago",
]
