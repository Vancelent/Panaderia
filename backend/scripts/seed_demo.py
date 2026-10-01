"""Carga datos de ejemplo en una base VACÍA (solo para desarrollo / demos).

    python -m scripts.seed_demo

Usuarios creados: admin, pamela (vendedora), palala (panadero); contraseña: demo-1234.
Se niega a correr si la base ya tiene usuarios.
"""

import random
import sys
from datetime import timedelta
from decimal import Decimal as D

from sqlalchemy import func, select

from app.core.security import hash_password
from app.db.base import utcnow
from app.db.session import SessionLocal, get_engine
from app.models import (
    Arqueo,
    Cliente,
    CompraMateriaPrima,
    DetallePedido,
    DetalleVenta,
    EstadoPedidoEnum,
    EstadoTurnoEnum,
    GastoVario,
    MateriaPrima,
    Merma,
    MetodoPagoEnum,
    Pedido,
    Producto,
    Proveedor,
    RecetaInsumo,
    RolEnum,
    Turno,
    Usuario,
    Venta,
    VentaPago,
)

MEDIOS = [MetodoPagoEnum.EFECTIVO, MetodoPagoEnum.TARJETA, MetodoPagoEnum.TRANSFERENCIA]
get_engine()
random.seed(7)
with SessionLocal() as s:
    if s.scalar(select(func.count()).select_from(Usuario)):
        sys.exit("La base ya tiene usuarios: el seed solo corre sobre una base vacía.")
    pw = hash_password("demo-1234")
    admin = Usuario(username="admin", nombre="Nelly", rol=RolEnum.ADMIN, hashed_password=pw)
    vend = Usuario(username="pamela", nombre="Pamela", rol=RolEnum.VENDEDORA, hashed_password=pw)
    pan = Usuario(username="palala", nombre="Palala", rol=RolEnum.PANADERO, hashed_password=pw)
    s.add_all([admin, vend, pan])
    s.flush()
    harina = MateriaPrima(
        nombre="Harina 000",
        unidad_medida="kg",
        stock_actual=D("80"),
        stock_minimo=D("25"),
        costo_unitario_actual=D("950"),
    )
    manteca = MateriaPrima(
        nombre="Manteca",
        unidad_medida="kg",
        stock_actual=D("4"),
        stock_minimo=D("5"),
        costo_unitario_actual=D("7800"),
    )
    azucar = MateriaPrima(
        nombre="Azúcar",
        unidad_medida="kg",
        stock_actual=D("12"),
        stock_minimo=D("8"),
        costo_unitario_actual=D("1300"),
    )
    levadura = MateriaPrima(
        nombre="Levadura",
        unidad_medida="kg",
        stock_actual=D("2.5"),
        stock_minimo=D("1"),
        costo_unitario_actual=D("6000"),
    )
    s.add_all([harina, manteca, azucar, levadura])
    s.flush()
    prods = [
        ("Pan francés (kg)", "Panes", "2800", 25, 10),
        ("Pan de campo", "Panes", "3500", 6, 4),
        ("Flauta", "Panes", "900", 30, 10),
        ("Medialuna de manteca", "Facturas", "450", 48, 24),
        ("Medialuna de grasa", "Facturas", "400", 36, 24),
        ("Vigilante", "Facturas", "500", 0, 12),
        ("Tortita negra", "Facturas", "450", 15, 12),
        ("Chipá (100 g)", "Salados", "1200", 12, 6),
        ("Prepizza", "Salados", "2200", 8, 4),
        ("Torta Rogel", "Tortas", "18500", 2, 1),
        ("Pastafrola", "Tortas", "9500", 3, 2),
        ("Alfajor de maicena", "Dulces", "800", 20, 10),
    ]
    P = []
    for n, c, pr, st, mn in prods:
        p = Producto(nombre=n, categoria=c, precio_venta=D(pr), stock_mostrador=st, stock_minimo=mn)
        s.add(p)
        P.append(p)
    s.flush()
    s.add_all(
        [
            RecetaInsumo(producto_id=P[0].id, materia_prima_id=harina.id, cantidad_necesaria=D("0.62")),
            RecetaInsumo(producto_id=P[0].id, materia_prima_id=levadura.id, cantidad_necesaria=D("0.015")),
            RecetaInsumo(producto_id=P[3].id, materia_prima_id=harina.id, cantidad_necesaria=D("0.035")),
            RecetaInsumo(producto_id=P[3].id, materia_prima_id=manteca.id, cantidad_necesaria=D("0.012")),
            RecetaInsumo(producto_id=P[3].id, materia_prima_id=azucar.id, cantidad_necesaria=D("0.006")),
        ]
    )
    prov = Proveedor(nombre="Molino San José", cuit="30-71234567-8", telefono="11 4444-5555")
    s.add(prov)
    s.flush()
    s.add(
        CompraMateriaPrima(
            proveedor_id=prov.id,
            materia_prima_id=harina.id,
            cantidad_comprada=D("50"),
            precio_total=D("47500"),
            fecha=utcnow() - timedelta(days=5),
        )
    )
    s.add(GastoVario(concepto="Luz", monto=D("68000"), fecha=utcnow() - timedelta(days=10)))
    # Historial de 30 días en turnos cerrados
    for dia in range(29, 0, -1):
        base = utcnow() - timedelta(days=dia)
        t = Turno(
            usuario_id=vend.id,
            efectivo_inicial=D("20000"),
            fecha_apertura=base.replace(hour=10),
            estado=EstadoTurnoEnum.CERRADO,
            fecha_cierre=base.replace(hour=20),
        )
        s.add(t)
        s.flush()
        tot_ef = D(0)
        for k in range(random.randint(8, 22)):
            m = random.choices(MEDIOS, weights=[6, 2, 3])[0]
            v = Venta(
                turno_id=t.id,
                usuario_id=vend.id,
                fecha=base.replace(hour=10) + timedelta(minutes=30 * k),
                metodo_pago=m,
                monto=D(0),
            )
            tot = D(0)
            for p in random.sample(P, random.randint(1, 3)):
                c = random.randint(1, 6)
                sub = D(p.precio_venta) * c
                tot += sub
                v.detalles.append(
                    DetalleVenta(producto_id=p.id, cantidad=c, precio_unitario=p.precio_venta, subtotal=sub)
                )
            v.monto = tot
            v.pagos.append(VentaPago(metodo_pago=m, monto=tot))
            s.add(v)
            if m == MetodoPagoEnum.EFECTIVO:
                tot_ef += tot
        esperado = D("20000") + tot_ef
        dif = D(random.choice([0, 0, 0, -500, 200, -1500]))
        s.add(
            Arqueo(
                turno_id=t.id,
                monto_sistema=esperado,
                monto_declarado=esperado + dif,
                diferencia=dif,
                ventas_efectivo=tot_ef,
                ventas_otros_medios=D(0),
                fecha=t.fecha_cierre,
            )
        )
    s.add(Merma(producto_id=P[3].id, usuario_id=vend.id, cantidad_perdida=4, motivo="Se cayó"))
    cli = Cliente(nombre="Bar La Esquina", telefono="11 5555-1234", direccion="Av. Corrientes 1234")
    s.add_all([cli, Cliente(nombre="María López", telefono="11 6666-7777")])
    s.flush()

    def pedido(estado, horas, items, **kw):
        det = [
            DetallePedido(
                producto_id=P[i].id,
                cantidad=c,
                precio_unitario=P[i].precio_venta,
                subtotal=D(P[i].precio_venta) * c,
            )
            for i, c in items
        ]
        s.add(
            Pedido(
                estado=estado,
                fecha_entrega=utcnow() + timedelta(hours=horas),
                total=sum(d.subtotal for d in det),
                creado_por_id=vend.id,
                detalles=det,
                **kw,
            )
        )

    pedido(EstadoPedidoEnum.PENDIENTE, 20, [(3, 60), (4, 24)], cliente_id=cli.id, notas="Retira a las 7:30")
    pedido(
        EstadoPedidoEnum.PENDIENTE,
        26,
        [(9, 1)],
        contacto="Sra. Gómez · 11 2222-3333",
        notas="Feliz cumple Sofi",
    )
    pedido(EstadoPedidoEnum.EN_PREPARACION, 3, [(0, 4), (7, 3)], contacto="Juan (vecino)")
    pedido(EstadoPedidoEnum.LISTO, 1, [(10, 1), (11, 6)], contacto="Laura · 11 8888-9999")
    s.commit()
print("seed ok")
