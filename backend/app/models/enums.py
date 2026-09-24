import enum

# En la BD se guardan los NOMBRES (ADMIN, ABIERTO...); la API expone los valores.
# Los nombres de clase determinan el nombre del tipo ENUM en Postgres
# (rolenum, estadoturnoenum...), por eso no deben renombrarse.


class RolEnum(str, enum.Enum):
    ADMIN = "Admin"
    ENCARGADA = "Encargada"
    VENDEDORA = "Vendedora"
    PANADERO = "Panadero"


class EstadoTurnoEnum(str, enum.Enum):
    ABIERTO = "Abierto"
    CERRADO = "Cerrado"


class MetodoPagoEnum(str, enum.Enum):
    EFECTIVO = "Efectivo"
    TARJETA = "Tarjeta"
    TRANSFERENCIA = "Transferencia"


class EstadoPedidoEnum(str, enum.Enum):
    PENDIENTE = "Pendiente"
    EN_PREPARACION = "En preparación"
    LISTO = "Listo"
    ENTREGADO = "Entregado"
    CANCELADO = "Cancelado"
