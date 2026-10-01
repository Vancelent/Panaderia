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
    EstadoPagoEnum,
    EstadoPedidoEnum,
    EstadoTurnoEnum,
    MetodoPagoEnum,
    RolEnum,
    TipoMovimientoCtaCteEnum,
)
from app.models.inventario import (
    ConversionDiaAnterior,
    LoteProduccion,
    MateriaPrima,
    Merma,
    Producto,
    RecetaInsumo,
)
from app.models.usuario import Usuario

__all__ = [
    "Arqueo",
    "Cliente",
    "CompraMateriaPrima",
    "ConversionDiaAnterior",
    "DescuentoPunto",
    "DetallePedido",
    "DetalleVenta",
    "EstadoPagoEnum",
    "EstadoPedidoEnum",
    "EstadoTurnoEnum",
    "GastoVario",
    "LoteProduccion",
    "MateriaPrima",
    "Merma",
    "MetodoPagoEnum",
    "MovimientoCuentaCorriente",
    "Pedido",
    "PlantillaEntrega",
    "Producto",
    "Proveedor",
    "PuntoEntrega",
    "RecetaInsumo",
    "RolEnum",
    "TipoMovimientoCtaCteEnum",
    "Turno",
    "Usuario",
    "Venta",
    "VentaPago",
]
