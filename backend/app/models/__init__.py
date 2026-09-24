"""Importa todos los modelos para que queden registrados en Base.metadata."""

from app.models.caja import Arqueo, DetalleVenta, Turno, Venta
from app.models.comercial import Cliente, DetallePedido, Pedido
from app.models.compras import CompraMateriaPrima, GastoVario, Proveedor
from app.models.enums import EstadoPedidoEnum, EstadoTurnoEnum, MetodoPagoEnum, RolEnum
from app.models.inventario import LoteProduccion, MateriaPrima, Merma, Producto, RecetaInsumo
from app.models.usuario import Usuario

__all__ = [
    "Arqueo",
    "Cliente",
    "CompraMateriaPrima",
    "DetallePedido",
    "DetalleVenta",
    "EstadoPedidoEnum",
    "EstadoTurnoEnum",
    "GastoVario",
    "LoteProduccion",
    "MateriaPrima",
    "Merma",
    "MetodoPagoEnum",
    "Pedido",
    "Producto",
    "Proveedor",
    "RecetaInsumo",
    "RolEnum",
    "Turno",
    "Usuario",
    "Venta",
]
