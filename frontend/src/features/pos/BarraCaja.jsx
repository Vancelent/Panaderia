import { AlertTriangle, History, Keyboard, LockKeyhole, Monitor, Pointer } from 'lucide-react'
import { Badge } from '../../components/ui/misc'
import { Button } from '../../components/ui/Button'
import { fmtHora } from '../../lib/format'

/** Acciones de la caja que son iguales en la vista de teclado y en la táctil. */
export default function BarraCaja({ turno, vista, onVista, onVentas, onMerma, onCierre, onRegistrarEquipo }) {
  return (
    <>
      <Badge tone="green" className="hidden h-8 px-3 sm:inline-flex">
        <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-500" />
        Turno #{turno.id} · {fmtHora(turno.fecha_apertura)}
      </Badge>
      <Button
        variant="secondary"
        size="icon"
        icon={vista === 'teclado' ? Pointer : Keyboard}
        onClick={onVista}
        title={vista === 'teclado' ? 'Cambiar a la vista táctil' : 'Cambiar a la vista de teclado'}
        aria-label={vista === 'teclado' ? 'Cambiar a la vista táctil' : 'Cambiar a la vista de teclado'}
      />
      {onRegistrarEquipo && (
        <Button
          variant="secondary"
          size="icon"
          icon={Monitor}
          onClick={onRegistrarEquipo}
          title="Registrar este equipo como caja (para ingresar con PIN)"
          aria-label="Registrar este equipo como caja"
        />
      )}
      <Button variant="secondary" size="icon" icon={History} onClick={onVentas} title="Últimas ventas" aria-label="Últimas ventas" />
      <Button variant="secondary" size="icon" icon={AlertTriangle} onClick={onMerma} title="Registrar merma" aria-label="Registrar merma" />
      <Button variant="secondary" icon={LockKeyhole} onClick={onCierre} title="Cerrar caja (F10)">
        <span className="hidden sm:inline">Cerrar caja</span>
      </Button>
    </>
  )
}
