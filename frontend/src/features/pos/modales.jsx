import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { LockKeyhole, Receipt } from 'lucide-react'
import { Button } from '../../components/ui/Button'
import { Field, Input } from '../../components/ui/Field'
import { Modal } from '../../components/ui/Modal'
import { Badge, EmptyState } from '../../components/ui/misc'
import { Spinner } from '../../components/ui/Spinner'
import { useToast } from '../../components/ui/toast'
import { mensajeError, post } from '../../lib/api'
import { fmtDinero, fmtHora } from '../../lib/format'
import { qk, useVentasTurno } from '../../lib/queries'

export function CierreModal({ open, onClose, carritoConItems }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [monto, setMonto] = useState('')
  const cerrar = useMutation({
    mutationFn: () => post('/turnos/actual/cierre', { monto_declarado: Number(monto) }),
    onSuccess: () => {
      toast.ok('Turno cerrado. ¡Gracias!')
      setMonto('')
      onClose()
      qc.setQueryData(qk.turnoActual, null)
      qc.removeQueries({ queryKey: qk.ventasTurno })
    },
    onError: (e) => toast.error(mensajeError(e)),
  })
  const valido = monto !== '' && Number(monto) >= 0

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="sm"
      title="Cerrar caja"
      description="Contá el efectivo del cajón e ingresá el total."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button variant="danger" icon={LockKeyhole} loading={cerrar.isPending} disabled={!valido} onClick={() => cerrar.mutate()}>
            Cerrar turno
          </Button>
        </>
      }
    >
      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (valido) cerrar.mutate()
        }}
        className="space-y-4"
      >
        {carritoConItems && (
          <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
            Hay productos en el ticket sin cobrar. Si cerrás, se descartan.
          </p>
        )}
        <Field label="Efectivo contado" hint="Incluí el fondo inicial. Tarjetas y transferencias no van.">
          {(id) => (
            <Input
              id={id}
              type="number"
              inputMode="decimal"
              step="0.01"
              min="0"
              className="tabular h-14 text-center text-2xl font-bold"
              value={monto}
              onChange={(e) => setMonto(e.target.value)}
            />
          )}
        </Field>
        <p className="text-xs text-stone-500">
          El sistema registra el arqueo y la encargada lo revisa. No se muestra la diferencia en caja.
        </p>
        <button type="submit" hidden />
      </form>
    </Modal>
  )
}

export function VentasTurnoModal({ open, onClose }) {
  const { data, isLoading } = useVentasTurno(open)
  return (
    <Modal open={open} onClose={onClose} title="Últimas ventas del turno">
      {isLoading ? (
        <div className="grid place-items-center py-10">
          <Spinner />
        </div>
      ) : !data?.length ? (
        <EmptyState icon={Receipt} title="Todavía no hay ventas en este turno" />
      ) : (
        <ul className="divide-y divide-stone-100 dark:divide-stone-800">
          {data.map((v) => (
            <li key={v.id} className="py-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-semibold">#{v.id}</span>
                  <span className="text-sm text-stone-500">{fmtHora(v.fecha)}</span>
                  {v.pagos.map((p, i) => (
                    <Badge key={i} tone={p.metodo_pago === 'Efectivo' ? 'green' : 'blue'}>
                      {p.metodo_pago}
                      {v.pagos.length > 1 ? ` ${fmtDinero(p.monto)}` : ''}
                    </Badge>
                  ))}
                </div>
                <span className="tabular font-bold">{fmtDinero(v.monto)}</span>
              </div>
              <p className="mt-1 text-sm text-stone-500">
                {v.detalles.map((d) => `${d.cantidad}× ${d.nombre}`).join(', ')}
              </p>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  )
}
