from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime, timezone
from app.database import get_db
from app.models.shift import Turno, Arqueo
from app.models.user import User, RoleEnum
from app.schemas.shift import TurnoCreate, TurnoResponse, TurnoCerrar, MensajeCierre

router = APIRouter(prefix="/turnos", tags=["Turnos y Arqueo Ciego"])

@router.post("/abrir", response_model=TurnoResponse, status_code=status.HTTP_201_CREATED)
async def abrir_turno(turno_in: TurnoCreate, db: AsyncSession = Depends(get_db)):
    # 1. Verificar si el usuario existe
    result = await db.execute(select(User).where(User.id == turno_in.user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
        
    # 2. Control de Permisos: Solo Ciertas personas abren caja
    if user.role not in [RoleEnum.VENDEDORA, RoleEnum.ENCARGADA, RoleEnum.ADMIN]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Rol no autorizado para abrir turno")
        
    # 3. Control: El usuario no debe tener un turno abierto paralelamente
    stmt = select(Turno).where(Turno.user_id == user.id, Turno.is_active == True)
    active_turno = (await db.execute(stmt)).scalar_one_or_none()
    
    if active_turno:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El usuario ya tiene un turno abierto")

    # 4. Abrir turno
    nuevo_turno = Turno(
        user_id=turno_in.user_id,
        fondo_fijo=turno_in.fondo_fijo,
        is_active=True
    )
    db.add(nuevo_turno)
    await db.commit()
    await db.refresh(nuevo_turno)
    
    return nuevo_turno

@router.post("/cerrar", response_model=MensajeCierre)
async def cerrar_turno(turno_in: TurnoCerrar, db: AsyncSession = Depends(get_db)):
    # 1. Buscar turno activo
    result = await db.execute(select(Turno).where(Turno.id == turno_in.turno_id))
    turno = result.scalar_one_or_none()
    
    if not turno:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Turno no encontrado")
    
    if not turno.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El turno ya se encuentra cerrado")

    # 2. Calcular montos internos (Arqueo) - Simulación de ventas
    # MOCK: Aquí sumarías todas las ventas cuyo turno_id == turno.id
    # stmt = select(func.sum(Venta.total)).where(Venta.turno_id == turno.id)
    # total_ventas = (await db.execute(stmt)).scalar() or 0.0
    ventas_del_turno = 0.0 
    
    # 3. Arqueo Ciego y Balance de Masas de Caja
    monto_sistema = turno.fondo_fijo + ventas_del_turno
    diferencia = turno_in.monto_declarado - monto_sistema
    
    arqueo = Arqueo(
        turno_id=turno.id,
        monto_sistema=monto_sistema,
        monto_declarado=turno_in.monto_declarado,
        diferencia=diferencia
    )
    
    # Cerrar turno actual
    turno.is_active = False
    turno.fecha_cierre = datetime.now(timezone.utc)
    
    db.add(arqueo)
    await db.commit()
    
    # ARQUEO CIEGO: La API responde de forma genérica.
    # El usuario cajero no verá cuanta 'diferencia' tuvo (si sobro o falto dinero).
    # Solo el contador/admin luego podrá revisar la tabla "arqueos".
    return MensajeCierre(
        message="Turno cerrado correctamente. Arqueo registrado ciegamente con éxito.",
        turno_id=turno.id
    )
