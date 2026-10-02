import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '../../components/ui/Button'
import { Field, Input } from '../../components/ui/Field'
import { Modal } from '../../components/ui/Modal'
import { Stepper } from '../../components/ui/misc'
import { useToast } from '../../components/ui/toast'
import { mensajeError, post } from '../../lib/api'

/** Carga del vehículo: lo que no se cargue de lo reservado vuelve a estar disponible para la caja. */
export default function CargaModal({ hoja, onClose }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [cargado, setCargado] = useState(() =>
    Object.fromEntries(hoja.carga.map((c) => [c.producto_id, c.reservada])),
  )
  const [fondo, setFondo] = useState('0')

  const total = Object.values(cargado).reduce((a, b) => a + b, 0)
  const sinCargar = hoja.carga.reduce((a, c) => a + (c.reservada - cargado[c.producto_id]), 0)

  const cargar = useMutation({
    mutationFn: () =>
      post(`/entregas/hojas/${hoja.id}/carga`, {
        items: hoja.carga.map((c) => ({ producto_id: c.producto_id, cantidad: cargado[c.producto_id] })),
        fondo_inicial: Number(fondo) || 0,
      }),
    onSuccess: () => {
      ;['hojas', 'hoja', 'resumen-entregas', 'productos', 'turnos-abiertos'].forEach((k) =>
        qc.invalidateQueries({ queryKey: [k] }),
      )
      toast.ok('Vehículo cargado: el stock salió del mostrador y se abrió el turno de reparto.')
      onClose()
    },
    onError: (e) => toast.error(mensajeError(e)),
  })

  return (
    <Modal
      open
      onClose={onClose}
      title="Cargar el vehículo"
      description="Indicá lo que realmente se cargó. Lo que falte de lo reservado queda disponible para la caja."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancelar
          </Button>
          <Button disabled={total === 0} loading={cargar.isPending} onClick={() => cargar.mutate()}>
            Confirmar carga
          </Button>
        </>
      }
    >
      <ul className="divide-y divide-stone-100 dark:divide-stone-800">
        {hoja.carga.map((c) => (
          <li key={c.producto_id} className="flex items-center justify-between gap-3 py-2.5">
            <div className="min-w-0">
              <p className="truncate font-semibold">{c.nombre}</p>
              <p className="text-xs text-stone-500">Reservado: {c.reservada}</p>
            </div>
            <Stepper
              value={cargado[c.producto_id]}
              min={0}
              max={c.reservada}
              onChange={(n) => setCargado((s) => ({ ...s, [c.producto_id]: n }))}
            />
          </li>
        ))}
      </ul>
      {sinCargar > 0 && (
        <p className="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
          {sinCargar} {sinCargar === 1 ? 'unidad no se carga' : 'unidades no se cargan'} y vuelven al stock vendible de la caja.
        </p>
      )}
      <Field className="mt-4" label="Cambio con el que sale el repartidor" hint="Fondo inicial en efectivo del turno de reparto.">
        {(id) => <Input id={id} type="number" min="0" step="0.01" inputMode="decimal" value={fondo} onChange={(e) => setFondo(e.target.value)} />}
      </Field>
    </Modal>
  )
}
