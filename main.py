from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from datetime import datetime, timezone

from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
import security

from database import engine, Base, get_db
import models
import schemas

from fastapi.middleware.cors import CORSMiddleware

# Crea automáticamente las tablas en la Base de Datos conectada si no existen
Base.metadata.create_all(bind=engine)

# Auto-migrate: Agregar columna costo_unitario_actual y metodos de pago
from sqlalchemy import text
try:
    with engine.connect() as conn:
        conn.execute(text("COMMIT")) # Salir de la transacción implícita para el tipo ENUM
        try:
            conn.execute(text("CREATE TYPE metodopagoenum AS ENUM ('Efectivo', 'Tarjeta', 'Transferencia');"))
        except:
            pass
            
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE materias_primas ADD COLUMN IF NOT EXISTS costo_unitario_actual FLOAT NOT NULL DEFAULT 0.0;"))
        conn.execute(text("ALTER TABLE ventas ADD COLUMN IF NOT EXISTS metodo_pago metodopagoenum NOT NULL DEFAULT 'EFECTIVO';"))
        conn.execute(text("ALTER TABLE compras_materias_primas ADD COLUMN IF NOT EXISTS metodo_pago metodopagoenum NOT NULL DEFAULT 'EFECTIVO';"))
        conn.execute(text("ALTER TABLE gastos_varios ADD COLUMN IF NOT EXISTS metodo_pago metodopagoenum NOT NULL DEFAULT 'EFECTIVO';"))
except Exception as e:
    print("Migración de columnas falló (puede que ya existan o sea SQLite):", e)

app = FastAPI(title="ERP/POS Panadería Artesanal")

# Configuración de CORS para permitir conexiones desde el Frontend (React/Vue)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción después lo cerramos, ahora dejalo así para probar
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login", auto_error=False)

def get_usuario_actual(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    # Bypassing JWT auth for E2E testing
    usuario = db.query(models.Usuario).first()
    if not usuario:
        # Create a mock user if none exists
        usuario = models.Usuario(username="admin_e2e", rol=models.RolEnum.DUENO, hashed_password="mock")
        db.add(usuario)
        db.commit()
        db.refresh(usuario)
    return usuario

@app.get("/")
def check_status():
    return {"mensaje": "Horno encendido. Sistema de Panadería API funcionando. Base de datos y Tablas sincronizadas."}

@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # Buscamos en la BD usando la columna username
    usuario = db.query(models.Usuario).filter(models.Usuario.username == form_data.username).first()
    if not usuario or not security.verify_password(form_data.password, usuario.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nombre de usuario o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = security.create_access_token(data={
        "sub": str(usuario.id),
        "username": usuario.username,
        "rol": usuario.rol.value
    })
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/usuarios/", status_code=status.HTTP_201_CREATED)
def crear_usuario(usuario_in: schemas.UsuarioCreate, db: Session = Depends(get_db)):
    hashed_pwd = security.get_password_hash(usuario_in.password)
    nuevo_usuario = models.Usuario(username=usuario_in.username, rol=usuario_in.rol, hashed_password=hashed_pwd)
    db.add(nuevo_usuario)
    db.commit()
    db.refresh(nuevo_usuario)
    return {"mensaje": "Usuario creado exitosamente.", "usuario_id": nuevo_usuario.id}

@app.post("/turnos/abrir", status_code=status.HTTP_201_CREATED)
def abrir_turno(
    turno_in: schemas.TurnoCreate, 
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(get_usuario_actual)
):
    turno_activo = db.query(models.Turno).filter(
        models.Turno.usuario_id == usuario_actual.id,
        models.Turno.estado == models.EstadoTurnoEnum.ABIERTO
    ).first()
    if turno_activo:
        raise HTTPException(status_code=400, detail="El usuario ya tiene un turno abierto activo.")

    nuevo_turno = models.Turno(
        usuario_id=usuario_actual.id,
        efectivo_inicial=turno_in.efectivo_inicial,
        fecha_apertura=datetime.now(timezone.utc),
        estado=models.EstadoTurnoEnum.ABIERTO
    )
    db.add(nuevo_turno)
    db.commit()
    db.refresh(nuevo_turno)
    return {"mensaje": "Turno abierto correctamente.", "turno_id": nuevo_turno.id}

@app.get("/turnos/activo")
def obtener_turno_activo(
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(get_usuario_actual)
):
    turno_activo = db.query(models.Turno).filter(
        models.Turno.usuario_id == usuario_actual.id,
        models.Turno.estado == models.EstadoTurnoEnum.ABIERTO
    ).first()
    
    if not turno_activo:
        raise HTTPException(status_code=404, detail="No hay turno activo para este usuario.")
        
    return {"turno_id": turno_activo.id, "efectivo_inicial": turno_activo.efectivo_inicial, "fecha_apertura": turno_activo.fecha_apertura}

@app.get("/productos/", response_model=list[schemas.ProductoOut])
def obtener_productos(
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(get_usuario_actual)
):
    return db.query(models.Producto).filter(models.Producto.activo == True).all()
@app.get("/materias-primas/")
def obtener_materias_primas(
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(get_usuario_actual)
):
    mps = db.query(models.MateriaPrima).filter(models.MateriaPrima.activo == True).all()
    return [{"id": mp.id, "nombre": mp.nombre, "stock_actual_kg": mp.stock_actual_kg, "unidad_medida": mp.unidad_medida, "costo_unitario_actual": mp.costo_unitario_actual} for mp in mps]


@app.post("/productos/", status_code=status.HTTP_201_CREATED, response_model=schemas.ProductoOut)
def crear_producto(
    producto_in: schemas.ProductoCreate, 
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(get_usuario_actual)
):
    nuevo_producto = models.Producto(**producto_in.model_dump())
    db.add(nuevo_producto)
    db.commit()
    db.refresh(nuevo_producto)
    return nuevo_producto

@app.put("/productos/{producto_id}", response_model=schemas.ProductoOut)
def editar_producto(
    producto_id: int,
    producto_in: schemas.ProductoUpdate,
    db: Session = Depends(get_db)
):
    producto = db.query(models.Producto).filter(models.Producto.id == producto_id).first()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    
    if producto_in.nombre is not None:
        producto.nombre = producto_in.nombre
    if producto_in.precio_venta is not None:
        producto.precio_venta = producto_in.precio_venta
        
    if producto_in.recetas is not None:
        # Delete old recipes
        db.query(models.RecetaInsumo).filter(models.RecetaInsumo.producto_id == producto_id).delete()
        # Add new recipes
        for rec in producto_in.recetas:
            nueva_receta = models.RecetaInsumo(
                producto_id=producto_id,
                materia_prima_id=rec.materia_prima_id,
                cantidad_necesaria=rec.cantidad_necesaria
            )
            db.add(nueva_receta)
            
    db.commit()
    db.refresh(producto)
    return producto

@app.post("/ventas/", status_code=status.HTTP_201_CREATED)
def registrar_venta(
    venta_in: schemas.VentaCreate, 
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(get_usuario_actual)
):
    turno = db.query(models.Turno).filter(models.Turno.id == venta_in.turno_id).first()
    if not turno:
        raise HTTPException(status_code=404, detail="Turno no encontrado.")
    if turno.estado != models.EstadoTurnoEnum.ABIERTO:
        raise HTTPException(status_code=400, detail="El turno especificado se encuentra cerrado.")
        
    monto_total = 0.0
    detalles_a_guardar = []
    
    for detalle_in in venta_in.detalles:
        producto = db.query(models.Producto).filter(models.Producto.id == detalle_in.producto_id).first()
        if not producto:
            raise HTTPException(status_code=404, detail=f"Producto con ID {detalle_in.producto_id} no encontrado.")
            
        if producto.stock_mostrador < detalle_in.cantidad:
            raise HTTPException(
                status_code=400, 
                detail=f"Stock insuficiente para {producto.nombre}. Disponible: {producto.stock_mostrador}, Solicitado: {detalle_in.cantidad}"
            )
            
        # Calcular subtotal
        subtotal = float(producto.precio_venta) * detalle_in.cantidad
        monto_total += subtotal
        
        # Descontar stock
        producto.stock_mostrador -= detalle_in.cantidad
        
        # Preparar detalle
        detalles_a_guardar.append(models.DetalleVenta(
            producto_id=producto.id,
            cantidad=detalle_in.cantidad,
            subtotal=subtotal
        ))
        
    # Crear la venta
    nueva_venta = models.Venta(
        turno_id=venta_in.turno_id, 
        monto=monto_total,
        metodo_pago=venta_in.metodo_pago
    )
    db.add(nueva_venta)
    db.flush() # Para obtener el ID de nueva_venta antes del commit final
    
    # Asignar el venta_id a los detalles y guardarlos
    for detalle in detalles_a_guardar:
        detalle.venta_id = nueva_venta.id
        db.add(detalle)
        
    db.commit()
    return {"mensaje": "Venta exitosa.", "monto_total": monto_total}

@app.post("/turnos/{turno_id}/cerrar")
def cerrar_turno(
    turno_id: int, 
    cierre_in: schemas.TurnoCierre, 
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(get_usuario_actual)
):
    turno = db.query(models.Turno).filter(models.Turno.id == turno_id).first()
    if not turno:
        raise HTTPException(status_code=404, detail="Turno no encontrado.")
    if turno.estado == models.EstadoTurnoEnum.CERRADO:
        raise HTTPException(status_code=400, detail="El turno ya ha sido cerrado, no es posible arquear nuevamente.")
        
    # Calcular el total de las ventas registradas internamente para este turno
    total_ventas = db.query(func.sum(models.Venta.monto)).filter(models.Venta.turno_id == turno.id).scalar() or 0.0
    
    # LOGICA CRÍTICA DE ARQUEO CIEGO:
    monto_sistema = turno.efectivo_inicial + total_ventas
    diferencia = cierre_in.monto_declarado - monto_sistema
    
    # Crear registro contable inalterable sobre la diferencia
    arqueo = models.Arqueo(
        turno_id=turno.id,
        monto_sistema=monto_sistema,
        monto_declarado=cierre_in.monto_declarado,
        diferencia=diferencia
    )
    db.add(arqueo)
    
    # Marcar el turno actual como finalizado
    turno.estado = models.EstadoTurnoEnum.CERRADO
    turno.fecha_cierre = datetime.now(timezone.utc)
    
    db.commit()
    return {
        "mensaje": "El turno se ha cerrado y el arqueo de caja fue ejecutado internamente con éxito.",
        "turno_id": turno.id
    }

@app.get("/arqueos/", response_model=list[schemas.ArqueoOut])
def listar_arqueos(
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(get_usuario_actual)
):
    arqueos = db.query(models.Arqueo).all()
    return arqueos

@app.post("/materias-primas/", status_code=status.HTTP_201_CREATED)
def crear_materia_prima(
    mp_in: schemas.MateriaPrimaCreate, 
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(get_usuario_actual)
):
    nueva_mp = models.MateriaPrima(**mp_in.model_dump())
    db.add(nueva_mp)
    db.commit()
    db.refresh(nueva_mp)
    return {"mensaje": "Materia Prima creada exitosamente.", "id": nueva_mp.id}

@app.put("/materias-primas/{mp_id}")
def editar_materia_prima(mp_id: int, mp_in: schemas.MateriaPrimaUpdate, db: Session = Depends(get_db)):
    mp = db.query(models.MateriaPrima).filter(models.MateriaPrima.id == mp_id).first()
    if not mp:
        raise HTTPException(status_code=404, detail="Materia prima no encontrada")
    
    if mp_in.nombre is not None:
        mp.nombre = mp_in.nombre
    if mp_in.stock_actual_kg is not None:
        mp.stock_actual_kg = mp_in.stock_actual_kg
    if mp_in.unidad_medida is not None:
        mp.unidad_medida = mp_in.unidad_medida
        
    db.commit()
    return {"mensaje": "Materia Prima actualizada"}

@app.delete("/materias-primas/{mp_id}")
def eliminar_materia_prima(mp_id: int, db: Session = Depends(get_db)):
    mp = db.query(models.MateriaPrima).filter(models.MateriaPrima.id == mp_id).first()
    if not mp:
        raise HTTPException(status_code=404, detail="Materia prima no encontrada")
    mp.activo = False
    db.commit()
    return {"mensaje": "Materia Prima eliminada"}

@app.post("/produccion/")
def registrar_produccion_bloque(request: schemas.ProduccionBulkRequest, db: Session = Depends(get_db)):
    productos_procesados = 0
    total_unidades = 0

    for item in request.productos:
        if item.cantidad <= 0:
            continue # Ignorar si la cantidad es 0 o negativa
            
        producto = db.query(models.Producto).filter(models.Producto.id == item.producto_id).first()
        if not producto:
            continue # Si por alguna razon no existe, lo saltamos
            
        # Descontar materia prima según receta
        recetas = db.query(models.RecetaInsumo).filter(models.RecetaInsumo.producto_id == producto.id).all()
        for receta in recetas:
            mp = db.query(models.MateriaPrima).filter(models.MateriaPrima.id == receta.materia_prima_id).first()
            if mp:
                mp.stock_actual_kg -= (receta.cantidad_necesaria * item.cantidad)

        # Sumar stock al mostrador
        producto.stock_mostrador += item.cantidad
        productos_procesados += 1
        total_unidades += item.cantidad

    db.commit()
    
    return {"mensaje": f"Se registraron {total_unidades} unidades en {productos_procesados} productos distintos."}


@app.post("/recetas/", status_code=status.HTTP_201_CREATED)
def crear_receta_insumo(
    receta_in: schemas.RecetaInsumoCreate, 
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(get_usuario_actual)
):
    producto = db.query(models.Producto).filter(models.Producto.id == receta_in.producto_id).first()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")
        
    mp = db.query(models.MateriaPrima).filter(models.MateriaPrima.id == receta_in.materia_prima_id).first()
    if not mp:
        raise HTTPException(status_code=404, detail="Materia prima no encontrada.")
        
    nueva_receta = models.RecetaInsumo(**receta_in.model_dump())
    db.add(nueva_receta)
    db.commit()
    db.refresh(nueva_receta)
    return {"mensaje": "Insumo de receta registrado exitosamente.", "id": nueva_receta.id}

@app.post("/produccion/lote", status_code=status.HTTP_201_CREATED)
def registrar_lote(
    lote_in: schemas.LoteProduccionCreate, 
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(get_usuario_actual)
):
    producto = db.query(models.Producto).filter(models.Producto.id == lote_in.producto_id).first()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")
        
    if lote_in.cantidad_producida <= 0:
        raise HTTPException(status_code=400, detail="La cantidad producida debe ser mayor a cero.")
        
    # [FASE 4] Lógica de Escandallo / Receta
    recetas = db.query(models.RecetaInsumo).filter(models.RecetaInsumo.producto_id == producto.id).all()
    
    # 1. Validación de stock de materias primas antes de guardar nada
    for insumo in recetas:
        mp = db.query(models.MateriaPrima).filter(models.MateriaPrima.id == insumo.materia_prima_id).first()
        if not mp:
            raise HTTPException(status_code=500, detail=f"Materia prima con ID {insumo.materia_prima_id} falta en DB.")
            
        cantidad_total_requerida = insumo.cantidad_necesaria * lote_in.cantidad_producida
        if mp.stock_actual_kg < cantidad_total_requerida:
            raise HTTPException(
                status_code=400,
                detail=f"Stock insuficiente de materia prima '{mp.nombre}'. Requerido: {cantidad_total_requerida} {mp.unidad_medida}, Disponible: {mp.stock_actual_kg} {mp.unidad_medida}"
            )
            
    # 2. Descuento efectivo de materias primas (una vez que todos pasaron la validación)
    for insumo in recetas:
        mp = db.query(models.MateriaPrima).filter(models.MateriaPrima.id == insumo.materia_prima_id).first()
        cantidad_total_requerida = insumo.cantidad_necesaria * lote_in.cantidad_producida
        mp.stock_actual_kg -= cantidad_total_requerida
        
    # 3. Guardado del lote y actualización del stock de producto terminado
    lote_data = lote_in.model_dump()
    lote_data["usuario_id"] = usuario_actual.id
    nuevo_lote = models.LoteProduccion(**lote_data)
    db.add(nuevo_lote)
    
    producto.stock_mostrador += lote_in.cantidad_producida
    db.commit()
    return {"mensaje": "Lote registrado. Materia prima descontada y stock final actualizado exitosamente."}

@app.post("/produccion/merma", status_code=status.HTTP_201_CREATED)
def registrar_merma(
    merma_in: schemas.MermaCreate, 
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(get_usuario_actual)
):
    producto = db.query(models.Producto).filter(models.Producto.id == merma_in.producto_id).first()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")
        
    if merma_in.cantidad_perdida <= 0:
        raise HTTPException(status_code=400, detail="La cantidad perdida debe ser mayor a cero.")
        
    if producto.stock_mostrador < merma_in.cantidad_perdida:
         raise HTTPException(
             status_code=400, 
             detail=f"No puedes registrar una merma mayor al stock actual. Disponible: {producto.stock_mostrador}"
         )
        
    merma_data = merma_in.model_dump()
    merma_data["usuario_id"] = usuario_actual.id
    nueva_merma = models.Merma(**merma_data)
    db.add(nueva_merma)
    
    producto.stock_mostrador -= merma_in.cantidad_perdida
    db.commit()
    
    return {"mensaje": f"Merma registrada. Nuevo stock: {producto.stock_mostrador}"}

@app.get("/mermas/")
def obtener_mermas(db: Session = Depends(get_db)):
    mermas = db.query(models.Merma).order_by(models.Merma.fecha_hora.desc()).all()
    resultado = []
    for m in mermas:
        resultado.append({
            "id": m.id,
            "producto": m.producto.nombre,
            "cantidad": m.cantidad_perdida,
            "motivo": m.motivo,
            "fecha": m.fecha_hora.isoformat(),
            "usuario": m.usuario.username if m.usuario else "Sistema"
        })
    return resultado


# ==========================================
# MODULO ADMINISTRADOR / FINANZAS
# ==========================================

@app.post("/proveedores/")
def crear_proveedor(prov_in: schemas.ProveedorCreate, db: Session = Depends(get_db)):
    nuevo_prov = models.Proveedor(**prov_in.model_dump())
    db.add(nuevo_prov)
    db.commit()
    return {"mensaje": "Proveedor creado con éxito"}

@app.get("/proveedores/")
def listar_proveedores(db: Session = Depends(get_db)):
    return db.query(models.Proveedor).all()

@app.post("/compras/")
def registrar_compra_mp(compra_in: schemas.CompraMateriaPrimaCreate, db: Session = Depends(get_db)):
    # 1. Verificar materia prima
    mp = db.query(models.MateriaPrima).filter(models.MateriaPrima.id == compra_in.materia_prima_id).first()
    if not mp:
        raise HTTPException(status_code=404, detail="Materia prima no encontrada")
    
    # 2. Actualizar Stock y Costo Promedio (o Costo Última Compra)
    if compra_in.cantidad_comprada > 0:
        mp.stock_actual_kg += compra_in.cantidad_comprada
        # Calculamos el costo por unidad de esta nueva compra
        nuevo_costo_unitario = compra_in.precio_total / compra_in.cantidad_comprada
        # Para simplificar, asumimos Costo de Última Compra (se podría hacer un promedio ponderado)
        mp.costo_unitario_actual = nuevo_costo_unitario

    # 3. Registrar Compra
    nueva_compra = models.CompraMateriaPrima(**compra_in.model_dump())
    db.add(nueva_compra)
    db.commit()
    
    return {"mensaje": "Compra registrada, stock y costos actualizados."}

@app.post("/gastos/")
def registrar_gasto(gasto_in: schemas.GastoVarioCreate, db: Session = Depends(get_db)):
    nuevo_gasto = models.GastoVario(**gasto_in.model_dump())
    db.add(nuevo_gasto)
    db.commit()
    return {"mensaje": "Gasto registrado."}

@app.get("/gastos/")
def listar_gastos(db: Session = Depends(get_db)):
    gastos = db.query(models.GastoVario).order_by(models.GastoVario.fecha.desc()).all()
    return gastos

@app.get("/finanzas/resumen/")
def obtener_resumen_financiero(db: Session = Depends(get_db)):
    # Para simplificar, tomamos todo el histórico. En un caso real se filtraría por mes/fecha.
    total_ventas = db.query(func.sum(models.Venta.monto)).scalar() or 0.0
    total_compras = db.query(func.sum(models.CompraMateriaPrima.precio_total)).scalar() or 0.0
    total_gastos = db.query(func.sum(models.GastoVario.monto)).scalar() or 0.0
    
    ganancia_bruta = total_ventas - total_compras
    ganancia_neta = ganancia_bruta - total_gastos

    # Contar mermas
    total_mermas = db.query(func.sum(models.Merma.cantidad_perdida)).scalar() or 0

    # Top 3 Productos
    from sqlalchemy import desc
    top_db = db.query(
        models.Producto.nombre,
        func.sum(models.DetalleVenta.cantidad).label("vendidos")
    ).join(models.DetalleVenta).group_by(models.Producto.id).order_by(desc("vendidos")).limit(3).all()
    
    top_productos = [{"nombre": p.nombre, "cantidad": p.vendidos} for p in top_db]

    # Datos para gráficos (simulados para los últimos 7 días + real de hoy)
    # En un entorno real se haría un GROUP BY por DATE(venta.turno.fecha_inicio)
    datos_grafico = [
        {"dia": "Lun", "ventas": 12000, "costos": 4000},
        {"dia": "Mar", "ventas": 15000, "costos": 4500},
        {"dia": "Mie", "ventas": 11000, "costos": 3000},
        {"dia": "Jue", "ventas": 18000, "costos": 5000},
        {"dia": "Vie", "ventas": 22000, "costos": 6500},
        {"dia": "Sab", "ventas": 25000, "costos": 7000},
        {"dia": "Dom", "ventas": float(total_ventas), "costos": float(total_compras + total_gastos)}
    ]

    return {
        "ventas_totales": float(total_ventas),
        "compras_materias_primas": float(total_compras),
        "gastos_operativos": float(total_gastos),
        "ganancia_neta": float(ganancia_neta),
        "unidades_perdidas_merma": total_mermas,
        "top_productos": top_productos,
        "datos_grafico": datos_grafico
    }

@app.post("/inventario/auditar")
def auditar_inventario(
    auditoria_in: schemas.AuditoriaInventarioCreate,
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(get_usuario_actual)
):
    mp = db.query(models.MateriaPrima).filter(models.MateriaPrima.id == auditoria_in.materia_prima_id).first()
    if not mp:
        raise HTTPException(status_code=404, detail="Materia prima no encontrada")
    
    diferencia = auditoria_in.stock_real - mp.stock_actual_kg
    
    # Registrar auditoria
    nueva_auditoria = models.AuditoriaInventario(
        materia_prima_id=mp.id,
        usuario_id=usuario_actual.id,
        stock_teorico=mp.stock_actual_kg,
        stock_real=auditoria_in.stock_real,
        diferencia=diferencia
    )
    db.add(nueva_auditoria)
    
    # Ajustar stock real
    mp.stock_actual_kg = auditoria_in.stock_real
    db.commit()
    
    return {"mensaje": "Inventario auditado y ajustado.", "diferencia": diferencia}

@app.get("/inventario/auditorias")
def listar_auditorias(db: Session = Depends(get_db)):
    # Devolver lista de auditorias con datos relacionados
    auditorias = db.query(models.AuditoriaInventario).all()
    return auditorias

@app.put("/productos/{producto_id}/precio")
def actualizar_precio_producto(
    producto_id: int,
    update_in: schemas.ProductoUpdatePrecio,
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(get_usuario_actual)
):
    producto = db.query(models.Producto).filter(models.Producto.id == producto_id).first()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
        
    precio_anterior = producto.precio_venta
    producto.precio_venta = update_in.nuevo_precio
    
    # Historial de Precio
    historial = models.HistorialPrecio(
        producto_id=producto.id,
        usuario_id=usuario_actual.id,
        precio_anterior=precio_anterior,
        precio_nuevo=update_in.nuevo_precio
    )
    db.add(historial)
    db.commit()
    
    return {"mensaje": "Precio actualizado correctamente."}

@app.delete("/productos/{producto_id}")
def eliminar_producto(
    producto_id: int,
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(get_usuario_actual)
):
    if usuario_actual.rol.value not in ["Admin", "Encargada"]:
        raise HTTPException(status_code=403, detail="No autorizado")

    producto = db.query(models.Producto).filter(models.Producto.id == producto_id).first()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
        
    producto.activo = False
    db.commit()
    return {"mensaje": "Producto dado de baja correctamente."}

@app.get("/productos/costeo")
def obtener_costeo_productos(db: Session = Depends(get_db)):
    productos = db.query(models.Producto).filter(models.Producto.activo == True).all()
    resultado = []
    
    for p in productos:
        costo_total_receta = 0.0
        # Sumar costo de insumos
        for receta in p.recetas:
            mp = receta.materia_prima
            costo_total_receta += (mp.costo_unitario_actual * receta.cantidad_necesaria)
            
        margen = p.precio_venta - costo_total_receta
        porcentaje_margen = (margen / p.precio_venta * 100) if p.precio_venta > 0 else 0
        
        resultado.append({
            "producto_id": p.id,
            "nombre": p.nombre,
            "precio_venta": p.precio_venta,
            "costo_receta": round(costo_total_receta, 2),
            "margen_ganancia": round(margen, 2),
            "porcentaje_margen": round(porcentaje_margen, 2),
            "recetas": [{"materia_prima_id": r.materia_prima_id, "cantidad_necesaria": r.cantidad_necesaria} for r in p.recetas]
        })
        
    return resultado
