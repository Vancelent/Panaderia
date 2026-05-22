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

# Auto-migrate: Agregar columna costo_unitario_actual si no existe
from sqlalchemy import text
try:
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE materias_primas ADD COLUMN IF NOT EXISTS costo_unitario_actual FLOAT NOT NULL DEFAULT 0.0;"))
except Exception as e:
    print("Migración de columna falló (puede que ya exista o sea SQLite):", e)

app = FastAPI(title="ERP/POS Panadería Artesanal")

# Configuración de CORS para permitir conexiones desde el Frontend (React/Vue)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción después lo cerramos, ahora dejalo así para probar
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_usuario_actual(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales o el token expiró",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, security.SECRET_KEY, algorithms=[security.ALGORITHM])
        usuario_id: str = payload.get("sub")
        if usuario_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    usuario = db.query(models.Usuario).filter(models.Usuario.id == int(usuario_id)).first()
    if usuario is None:
        raise credentials_exception
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
    return db.query(models.Producto).all()

@app.get("/materias-primas/")
def obtener_materias_primas(
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(get_usuario_actual)
):
    mps = db.query(models.MateriaPrima).all()
    # Retornamos formato diccionario por simplicidad ya que no tenemos MateriaPrimaOut
    return [{"id": mp.id, "nombre": mp.nombre, "stock_actual_kg": mp.stock_actual_kg, "unidad_medida": mp.unidad_medida} for mp in mps]


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
    nueva_venta = models.Venta(turno_id=venta_in.turno_id, monto=monto_total)
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

    return {
        "ventas_totales": float(total_ventas),
        "compras_materias_primas": float(total_compras),
        "gastos_operativos": float(total_gastos),
        "ganancia_neta": float(ganancia_neta),
        "unidades_perdidas_merma": total_mermas
    }
