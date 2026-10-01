import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, History, Undo2 } from 'lucide-react'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Field'
import { Modal } from '../../components/ui/Modal'
import { Badge, EmptyState, ErrorState, Stepper } from '../../components/ui/misc'
import { PantallaCarga } from '../../components/ui/Spinner'
import { useToast } from '../../components/ui/toast'
import { mensajeError, post } from '../../lib/api'
import { fmtDinero, fmtHora } from '../../lib/format'
import { qk, useDiaAnterior } from '../../lib/queries'

/** Ajuste manual de la encargada: pasa unidades del producto fresco a su variante "día anterior". */
export default function DiaAnteriorPanel() {
  const qc = useQueryClient()
  const toast = useToast()
  const { data, isLoading, isError, error, refetch } = useDiaAnterior()
  const [cantidades, setCantidades] = useState({})
  const [motivo, setMotivo] = useState('')
  const [confirmar, setConfirmar] = useState(false)

  const alTerminar = (r) => {
    qc.setQueryData(qk.diaAnterior, r)
    qc.invalidateQueries({ queryKey: ['productos'] })
  }
  const pasar = useMutation({
    mutationFn: (items) => post('/stock/dia-anterior', { items, motivo: motivo.trim() || null }),
    onSuccess: (r) => {
      alTerminar(r)
      toast.ok('Listo: el stock pasó a día anterior.')
      setCantidades({})
      setMotivo('')
      setConfirmar(false)
    },
    onError: (e) => {
      setConfirmar(false)
      toast.error(mensajeError(e))
      qc.invalidateQueries({ queryKey: qk.diaAnterior })
    },
  })
  const revertir = useMutation({
    mutationFn: (id) => post(`/stock/dia-anterior/${id}/reversion`),
    onSuccess: (r) => {
      alTerminar(r)
      toast.ok('Conversión deshecha.')
    },
    onError: (e) => toast.error(mensajeError(e)),
  })

  if (isLoading) return <PantallaCarga />
  if (isError) return <ErrorState error={error} onRetry={refetch} />

  const filas = data.productos
  const items = filas
    .map((f) => ({ fila: f, cantidad: cantidades[f.producto_id] ?? 0 }))
    .filter((i) => i.cantidad > 0)
  const unidades = items.reduce((t, i) => t + i.cantidad, 0)

  if (!filas.length) {
    return (
      <div className="card">
        <EmptyState icon={History} title="Todavía no hay productos con variante de día anterior">
          Creá la variante desde Productos: nuevo producto con &quot;Es variante de&quot; el producto fresco y su precio con descuento.
        </EmptyState>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <p className="max-w-2xl text-sm text-stone-600 dark:text-stone-400">
        Decidí vos qué sobrante sigue en condiciones de venderse. Las unidades pasan del producto fresco a su variante
        &quot;día anterior&quot;, que se vende con su propio precio. No se toca lo reservado para el reparto.
      </p>

      <div className="card divide-y divide-stone-100 dark:divide-stone-800">
        {filas.map((f) => (
          <div key={f.producto_id} className="flex flex-wrap items-center gap-x-4 gap-y-2 p-4">
            <div className="min-w-[180px] flex-1">
              <p className="font-semibold">{f.nombre}</p>
              <p className="text-sm text-stone-500">
                Disponible: <strong className="tabular text-stone-800 dark:text-stone-200">{f.stock_disponible}</strong>
                {f.stock_disponible !== f.stock_mostrador && ` (${f.stock_mostrador - f.stock_disponible} reservadas)`}
              </p>
            </div>
            <ArrowRight className="hidden h-4 w-4 text-stone-400 sm:block" aria-hidden />
            <div className="min-w-[180px] flex-1">
              <p className="font-medium">{f.variante_nombre}</p>
              <p className="tabular text-sm text-stone-500">
                Hay {f.variante_stock} · {fmtDinero(f.variante_precio)}
              </p>
            </div>
            <Stepper
              value={cantidades[f.producto_id] ?? 0}
              max={f.stock_disponible}
              onChange={(n) => setCantidades((c) => ({ ...c, [f.producto_id]: n }))}
              size="lg"
            />
          </div>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Input
          className="max-w-xs"
          placeholder="Motivo (opcional)"
          maxLength={200}
          value={motivo}
          onChange={(e) => setMotivo(e.target.value)}
        />
        <Button size="lg" disabled={unidades === 0} onClick={() => setConfirmar(true)}>
          Pasar a día anterior{unidades > 0 && ` (${unidades})`}
        </Button>
      </div>

      <section>
        <h2 className="mb-2 flex items-center gap-2 font-bold">
          <History className="h-4 w-4" /> Conversiones de hoy
        </h2>
        {data.conversiones_hoy.length === 0 ? (
          <p className="text-sm text-stone-500">Todavía no pasaste nada a día anterior hoy.</p>
        ) : (
          <ul className="card divide-y divide-stone-100 dark:divide-stone-800">
            {data.conversiones_hoy.map((c) => (
              <li key={c.id} className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
                <span className="tabular text-stone-500">{fmtHora(c.fecha)}</span>
                <span className="min-w-0 flex-1">
                  <strong className="tabular">{c.cantidad}</strong> × {c.producto}
                  {c.revierte_id ? ' (vuelve al producto fresco)' : ` → ${c.variante}`}
                  <span className="text-stone-500"> · {c.usuario}</span>
                  {c.motivo && <span className="text-stone-500"> · {c.motivo}</span>}
                </span>
                {c.revertida && <Badge>Deshecha</Badge>}
                {c.revierte_id && <Badge tone="blue">Reversión</Badge>}
                {c.se_puede_revertir && (
                  <Button
                    size="sm"
                    variant="ghost"
                    icon={Undo2}
                    loading={revertir.isPending && revertir.variables === c.id}
                    onClick={() => revertir.mutate(c.id)}
                  >
                    Deshacer
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <Modal
        open={confirmar}
        onClose={() => setConfirmar(false)}
        title="Confirmar pase a día anterior"
        description="Todo o nada: si falta stock en algún producto, no se mueve ninguno."
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmar(false)}>
              Revisar
            </Button>
            <Button
              loading={pasar.isPending}
              onClick={() => pasar.mutate(items.map((i) => ({ producto_id: i.fila.producto_id, cantidad: i.cantidad })))}
            >
              Confirmar
            </Button>
          </>
        }
      >
        <ul className="divide-y divide-stone-100 dark:divide-stone-800">
          {items.map(({ fila, cantidad }) => (
            <li key={fila.producto_id} className="flex justify-between py-2">
              <span>
                {fila.nombre} <span className="text-stone-500">→ {fila.variante_nombre}</span>
              </span>
              <span className="tabular font-bold">{cantidad}</span>
            </li>
          ))}
        </ul>
      </Modal>
    </div>
  )
}
