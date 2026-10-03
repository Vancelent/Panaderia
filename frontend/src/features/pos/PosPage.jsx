import { useCallback, useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Banknote } from 'lucide-react'
import { useAuth } from '../../auth/context'
import { Button } from '../../components/ui/Button'
import { Field, Input } from '../../components/ui/Field'
import { ErrorState } from '../../components/ui/misc'
import { PantallaCarga } from '../../components/ui/Spinner'
import { useToast } from '../../components/ui/toast'
import { mensajeError, post } from '../../lib/api'
import { qk, useProductos, useTurnoActual } from '../../lib/queries'
import { esGestion } from '../../lib/roles'
import { MermaModal } from '../stock/MermaModal'
import RegistrarEquipoModal from '../admin/RegistrarEquipoModal'
import { CobroModal } from './CobroModal'
import { CierreModal, VentasTurnoModal } from './modales'
import PosTactil from './PosTactil'
import PosTeclado from './PosTeclado'
import { usePos } from './usePos'

const CLAVE_VISTA = 'pos_vista'

/** La vista se elige por capacidad del dispositivo (puntero grueso = táctil) o por la preferencia guardada. */
function vistaInicial() {
  try {
    const guardada = localStorage.getItem(CLAVE_VISTA)
    if (guardada === 'teclado' || guardada === 'tactil') return guardada
  } catch {
    // Sin almacenamiento (modo privado): se usa la detección
  }
  return window.matchMedia?.('(pointer: coarse)').matches ? 'tactil' : 'teclado'
}

export default function PosPage() {
  const turno = useTurnoActual()
  if (turno.isLoading) return <PantallaCarga texto="Verificando turno…" />
  if (turno.isError) return <ErrorState error={turno.error} onRetry={turno.refetch} />
  return turno.data ? <Terminal turno={turno.data} /> : <AbrirTurno />
}

function AbrirTurno() {
  const qc = useQueryClient()
  const toast = useToast()
  const { user } = useAuth()
  const [monto, setMonto] = useState('')
  const abrir = useMutation({
    mutationFn: () => post('/turnos', { efectivo_inicial: Number(monto) }),
    onSuccess: (t) => {
      qc.setQueryData(qk.turnoActual, t)
      toast.ok('Turno abierto. ¡Buenas ventas!')
    },
    onError: (e) => toast.error(mensajeError(e)),
  })
  const valido = monto !== '' && Number(monto) >= 0

  return (
    <div className="flex min-h-[70vh] items-center justify-center">
      <form
        className="card w-full max-w-sm p-6"
        onSubmit={(e) => {
          e.preventDefault()
          if (valido) abrir.mutate()
        }}
      >
        <div className="mb-5 flex items-center gap-3">
          <div className="grid h-12 w-12 place-items-center rounded-2xl bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
            <Banknote className="h-6 w-6" />
          </div>
          <div>
            <h1 className="text-xl font-bold">Abrir caja</h1>
            <p className="text-sm text-stone-500">Hola {user.nombre || user.username}, contá el fondo inicial.</p>
          </div>
        </div>
        <Field label="Efectivo en el cajón" hint="Billetes y monedas con los que arrancás el turno.">
          {(id) => (
            <Input
              id={id}
              type="number"
              inputMode="decimal"
              step="0.01"
              min="0"
              autoFocus
              className="tabular h-14 text-center text-2xl font-bold"
              placeholder="$ 0,00"
              value={monto}
              onChange={(e) => setMonto(e.target.value)}
            />
          )}
        </Field>
        <Button type="submit" variant="success" size="lg" className="mt-5 w-full" loading={abrir.isPending} disabled={!valido}>
          Iniciar turno
        </Button>
      </form>
    </div>
  )
}

function Terminal({ turno }) {
  const { user } = useAuth()
  const pos = usePos()
  const productos = useProductos()
  const [vista, setVista] = useState(vistaInicial)
  const [modal, setModal] = useState(null) // 'cobro' | 'cierre' | 'merma' | 'ventas' | 'equipo'

  const cambiarVista = () =>
    setVista((v) => {
      const nueva = v === 'teclado' ? 'tactil' : 'teclado'
      try {
        localStorage.setItem(CLAVE_VISTA, nueva)
      } catch {
        // La preferencia no se guarda, pero la vista cambia igual
      }
      return nueva
    })

  const abrirCobro = useCallback(() => setModal('cobro'), [])
  const barra = useMemo(
    () => ({
      turno,
      vista,
      onVista: cambiarVista,
      onVentas: () => setModal('ventas'),
      onMerma: () => setModal('merma'),
      onCierre: () => setModal('cierre'),
      // "Registrar este equipo como caja": solo la gestión (docs/rfc-001 §2.3)
      onRegistrarEquipo: esGestion(user) ? () => setModal('equipo') : undefined,
    }),
    [turno, vista, user],
  )

  const Vista = vista === 'teclado' ? PosTeclado : PosTactil
  return (
    <>
      <Vista pos={pos} barra={barra} abrirCobro={abrirCobro} modalAbierto={modal !== null} />

      {modal === 'cobro' && (
        <CobroModal
          open
          onClose={() => setModal(null)}
          items={pos.items}
          totalCentavos={pos.totalCentavos}
          onVendido={() => {
            pos.despachar({ tipo: 'vendido' })
            setModal(null)
          }}
        />
      )}
      <CierreModal open={modal === 'cierre'} onClose={() => setModal(null)} carritoConItems={pos.lineas.length > 0} />
      <MermaModal open={modal === 'merma'} onClose={() => setModal(null)} productos={productos.data ?? []} />
      <VentasTurnoModal open={modal === 'ventas'} onClose={() => setModal(null)} />
      <RegistrarEquipoModal open={modal === 'equipo'} onClose={() => setModal(null)} />
    </>
  )
}
