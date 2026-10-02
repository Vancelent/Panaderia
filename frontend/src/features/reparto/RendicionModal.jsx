import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '../../components/ui/Button'
import { Field, Input } from '../../components/ui/Field'
import { Modal } from '../../components/ui/Modal'
import { Stepper } from '../../components/ui/misc'
import { useToast } from '../../components/ui/toast'
import { mensajeError, post } from '../../lib/api'

/**
 * Rendición de la hoja. Lo que vuelve (cargado − entregado) se reparte entre "vuelve al stock"
 * (como pan del día anterior si el producto tiene esa variante) y merma. El efectivo se declara
 * a ciegas: acá no se muestra cuánto debería haber.
 */
export default function RendicionModal({ hoja, pendientes, onClose, onRendida }) {
  const toast = useToast()
  const qc = useQueryClient()
  const vuelve = hoja.carga
    .map((c) => ({ ...c, esperado: c.cargada - c.entregada }))
    .filter((c) => c.esperado > 0)
  const [merma, setMerma] = useState({})
  const [efectivo, setEfectivo] = useState('')

  const rendir = useMutation({
    mutationFn: () =>
      post(`/entregas/hojas/${hoja.id}/rendicion`, {
        devoluciones: vuelve.flatMap((c) => {
          const m = merma[c.producto_id] ?? 0
          return [
            ...(c.esperado - m > 0
              ? [{ producto_id: c.producto_id, cantidad: c.esperado - m, destino: 'Reingreso' }]
              : []),
            ...(m > 0 ? [{ producto_id: c.producto_id, cantidad: m, destino: 'Merma' }] : []),
          ]
        }),
        efectivo_declarado: Number(efectivo),
      }),
    onSuccess: () => {
      ;['hojas', 'hoja', 'resumen-entregas', 'productos', 'arqueos', 'turnos-abiertos', 'recorrido', 'saldos'].forEach(
        (k) => qc.invalidateQueries({ queryKey: [k] }),
      )
      toast.ok('Hoja rendida y turno de reparto cerrado.')
      onRendida()
    },
    onError: (e) => toast.error(mensajeError(e)),
  })

  const valido = efectivo !== '' && Number(efectivo) >= 0

  return (
    <Modal
      open
      onClose={onClose}
      title="Rendir la hoja"
      description="Registrá lo que volvió y el efectivo que entregó el repartidor."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancelar
          </Button>
          <Button variant="success" disabled={!valido} loading={rendir.isPending} onClick={() => rendir.mutate()}>
            Rendir y cerrar turno
          </Button>
        </>
      }
    >
      {pendientes > 0 && (
        <p className="mb-4 rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
          {pendientes} {pendientes === 1 ? 'parada sin resolver se cerrará' : 'paradas sin resolver se cerrarán'} como
          «No entregada» y su mercadería vuelve en la rendición.
        </p>
      )}

      <h3 className="mb-1 text-sm font-bold">Mercadería que vuelve</h3>
      {vuelve.length === 0 ? (
        <p className="text-sm text-stone-500">Se entregó todo lo cargado: no hay devoluciones.</p>
      ) : (
        <ul className="divide-y divide-stone-100 dark:divide-stone-800">
          {vuelve.map((c) => {
            const m = merma[c.producto_id] ?? 0
            return (
              <li key={c.producto_id} className="flex flex-wrap items-center justify-between gap-3 py-2.5">
                <div className="min-w-0">
                  <p className="truncate font-semibold">{c.nombre}</p>
                  <p className="text-xs text-stone-500">
                    Vuelven {c.esperado} · al stock {c.esperado - m} · merma {m}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-stone-500">Merma</span>
                  <Stepper
                    value={m}
                    min={0}
                    max={c.esperado}
                    onChange={(n) => setMerma((s) => ({ ...s, [c.producto_id]: n }))}
                  />
                </div>
              </li>
            )
          })}
        </ul>
      )}

      <Field
        className="mt-5"
        label="Efectivo entregado por el repartidor"
        hint="Contá todo el efectivo (incluido el cambio inicial). La diferencia no se muestra: queda en el arqueo para la gestión."
      >
        {(id) => (
          <Input
            id={id}
            type="number"
            min="0"
            step="0.01"
            inputMode="decimal"
            value={efectivo}
            onChange={(e) => setEfectivo(e.target.value)}
            placeholder="0,00"
          />
        )}
      </Field>
    </Modal>
  )
}
