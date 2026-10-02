import enum

# En la BD se guardan los NOMBRES (ADMIN, ABIERTO...); la API expone los valores.
# Los nombres de clase determinan el nombre del tipo ENUM en Postgres
# (rolenum, estadoturnoenum...), por eso no deben renombrarse.


class RolEnum(str, enum.Enum):
    ADMIN = "Admin"
    ENCARGADA = "Encargada"
    VENDEDORA = "Vendedora"
    PANADERO = "Panadero"
    REPARTIDOR = "Repartidor"


class EstadoTurnoEnum(str, enum.Enum):
    ABIERTO = "Abierto"
    CERRADO = "Cerrado"


class MetodoPagoEnum(str, enum.Enum):
    EFECTIVO = "Efectivo"
    TARJETA = "Tarjeta"
    TRANSFERENCIA = "Transferencia"
    QR = "QR"
    CUENTA_CORRIENTE = "Cuenta corriente"


class EstadoPagoEnum(str, enum.Enum):
    """Hoy todo pago nace APROBADO; PENDIENTE y RECHAZADO quedan para posnet/QR."""

    APROBADO = "Aprobado"
    PENDIENTE = "Pendiente"
    RECHAZADO = "Rechazado"


class TipoMovimientoCtaCteEnum(str, enum.Enum):
    CARGO = "Cargo"
    PAGO = "Pago"
    NOTA_CREDITO = "Nota de crédito"
    AJUSTE = "Ajuste"


class EstadoPedidoEnum(str, enum.Enum):
    PENDIENTE = "Pendiente"
    EN_PREPARACION = "En preparación"
    LISTO = "Listo"
    ENTREGADO = "Entregado"
    CANCELADO = "Cancelado"


class TipoTurnoEnum(str, enum.Enum):
    MOSTRADOR = "Mostrador"
    REPARTO = "Reparto"


class OrigenVentaEnum(str, enum.Enum):
    MOSTRADOR = "Mostrador"
    PEDIDO = "Pedido"
    REPARTO = "Reparto"


class EstadoHojaRutaEnum(str, enum.Enum):
    BORRADOR = "Borrador"
    CONFIRMADA = "Confirmada"
    CARGADA = "Cargada"
    EN_RUTA = "En ruta"
    RENDIDA = "Rendida"
    ANULADA = "Anulada"


class EstadoEntregaEnum(str, enum.Enum):
    PENDIENTE = "Pendiente"
    EN_LOCAL = "En el local"
    ENTREGADA = "Entregada"
    PARCIAL = "Parcial"
    NO_ENTREGADA = "No entregada"


class TipoEventoEntregaEnum(str, enum.Enum):
    CHECK_IN = "Check-in"
    CONFIRMADA = "Confirmada"
    NO_ENTREGADA = "No entregada"
    NOTA = "Nota"


class TipoEventoRecorridoEnum(str, enum.Enum):
    GPS_SIN_SENAL = "GPS sin señal"
    PERMISO_REVOCADO = "Permiso revocado"
    TRAZA_INTERRUMPIDA = "Traza interrumpida"


class DestinoDevolucionEnum(str, enum.Enum):
    """Qué pasa con la mercadería que vuelve del reparto (solo en la API, no se guarda como tipo)."""

    REINGRESO = "Reingreso"
    MERMA = "Merma"
