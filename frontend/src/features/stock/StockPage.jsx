import { useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Package, Pencil, Search, Wheat } from 'lucide-react'
import { useAuth } from '../../auth/context'
import { Button } from '../../components/ui/Button'
import { Field, Input } from '../../components/ui/Field'
import { Modal } from '../../components/ui/Modal'
import { Badge, EmptyState, ErrorState, PageHeader, Segmented } from '../../components/ui/misc'
import { PantallaCarga } from '../../components/ui/Spinner'
import { useToast } from '../../components/ui/toast'
import { mensajeError, patch, put } from '../../lib/api'
import { fmtDinero, fmtNumero } from '../../lib/format'
import { useMateriasPrimas, useProductos } from '../../lib/queries'
import { esGestion } from '../../lib/roles'
import { nivelStock } from '../../lib/stock'
import DiaAnteriorPanel from './DiaAnteriorPanel'

const ORDEN = { red: 0, amber: 1, green: 2 }

function BarraNivel({ actual, minimo }) {
  const n = nivelStock(actual, minimo)
  // Escala: el mínimo queda al 40% de la barra
  const tope = Math.max(Number(minimo) * 2.5, Number(actual), 1)
  const pct = Math.min(100, (Number(actual) / tope) * 100)
  const color = { red: 'bg-red-500', amber: 'bg-amber-500', green: 'bg-emerald-500' }[n.tone]
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-stone-200 dark:bg-stone-800" aria-hidden>
      <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
    </div>
  )
}

export default function StockPage() {
  const { user } = useAuth()
  const gestion = esGestion(user)
  const [vista, setVista] = useState('productos')
  const [busqueda, setBusqueda] = useState('')
  const [soloAlertas, setSoloAlertas] = useState(false)
  const [editando, setEditando] = useState(null)
  const productos = useProductos()
  const insumos = useMateriasPrimas()

  const q = vista === 'productos' ? productos : insumos
  const filas = useMemo(() => {
    const t = busqueda.trim().toLowerCase()
    return (q.data ?? [])
      .map((x) => {
        const actual = vista === 'productos' ? x.stock_mostrador : x.stock_actual
        return { ...x, actual, nivel: nivelStock(actual, x.stock_minimo) }
      })
      .filter((x) => !t || x.nombre.toLowerCase().includes(t))
      .filter((x) => !soloAlertas || x.nivel.tone !== 'green')
      .sort((a, b) => ORDEN[a.nivel.tone] - ORDEN[b.nivel.tone] || a.nombre.localeCompare(b.nombre))
  }, [q.data, vista, busqueda, soloAlertas])

  const alertas = (lista, campo) =>
    (lista ?? []).filter((x) => nivelStock(x[campo], x.stock_minimo).tone !== 'green').length

  return (
    <div>
      <PageHeader title="Stock" subtitle="Semáforo: rojo sin stock o bajo el mínimo, ámbar para reponer pronto." />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Segmented
          value={vista}
          onChange={setVista}
          options={[
            { value: 'productos', label: 'Mostrador', count: alertas(productos.data, 'stock_mostrador') || null },
            { value: 'insumos', label: 'Insumos', count: alertas(insumos.data, 'stock_actual') || null },
            ...(gestion ? [{ value: 'dia-anterior', label: 'Día anterior' }] : []),
          ]}
        />
        {vista !== 'dia-anterior' && (
          <>
            <div className="relative min-w-[200px] flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-stone-400" />
              <Input className="pl-9" placeholder="Buscar…" value={busqueda} onChange={(e) => setBusqueda(e.target.value)} />
            </div>
            <label className="flex cursor-pointer items-center gap-2 text-sm font-medium">
              <input type="checkbox" className="h-4 w-4 accent-brand-600" checked={soloAlertas} onChange={(e) => setSoloAlertas(e.target.checked)} />
              Solo alertas
            </label>
          </>
        )}
      </div>

      {vista === 'dia-anterior' ? (
        <DiaAnteriorPanel />
      ) : q.isLoading ? (
        <PantallaCarga />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={q.refetch} />
      ) : filas.length === 0 ? (
        <div className="card">
          <EmptyState icon={vista === 'productos' ? Package : Wheat} title="Nada para mostrar" />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {filas.map((x) => (
            <div key={x.id} className="card p-4">
              <div className="mb-3 flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-semibold">{x.nombre}</p>
                  <p className="text-xs text-stone-500">
                    {vista === 'productos'
                      ? `${x.categoria ?? 'Sin categoría'} · ${fmtDinero(x.precio_venta)}`
                      : `Costo ${fmtDinero(x.costo_unitario_actual)} / ${x.unidad_medida}`}
                  </p>
                </div>
                <Badge tone={x.nivel.tone}>{x.nivel.label}</Badge>
              </div>
              <div className="mb-2 flex items-baseline justify-between">
                <span className="tabular text-2xl font-extrabold">
                  {fmtNumero(x.actual)}
                  <span className="ml-1 text-sm font-medium text-stone-500">{vista === 'productos' ? 'u' : x.unidad_medida}</span>
                </span>
                <span className="text-xs text-stone-500">mín. {fmtNumero(x.stock_minimo)}</span>
              </div>
              <BarraNivel actual={x.actual} minimo={x.stock_minimo} />
              {gestion && (
                <Button size="sm" variant="ghost" icon={Pencil} className="-mb-1 mt-3" onClick={() => setEditando({ ...x, tipo: vista })}>
                  Ajustar
                </Button>
              )}
            </div>
          ))}
        </div>
      )}
      {editando && <AjusteModal item={editando} onClose={() => setEditando(null)} />}
    </div>
  )
}

function AjusteModal({ item, onClose }) {
  const qc = useQueryClient()
  const toast = useToast()
  const esProducto = item.tipo === 'productos'
  const [actual, setActual] = useState(String(item.actual))
  const [minimo, setMinimo] = useState(String(item.stock_minimo))

  const guardar = useMutation({
    mutationFn: async () => {
      if (esProducto) {
        if (Number(actual) !== item.actual) await put(`/productos/${item.id}/stock`, { stock_mostrador: Number(actual) })
        if (Number(minimo) !== item.stock_minimo) await patch(`/productos/${item.id}`, { stock_minimo: Number(minimo) })
      } else {
        await patch(`/materias-primas/${item.id}`, { stock_actual: actual, stock_minimo: minimo })
      }
    },
    onSuccess: () => {
      toast.ok('Stock actualizado.')
      qc.invalidateQueries({ queryKey: esProducto ? ['productos'] : ['materias-primas'] })
      onClose()
    },
    onError: (e) => toast.error(mensajeError(e)),
  })

  return (
    <Modal
      open
      onClose={onClose}
      size="sm"
      title={`Ajustar: ${item.nombre}`}
      description="Usalo para corregir con un conteo físico. Las ventas, producción y compras ya mueven el stock solas."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button loading={guardar.isPending} onClick={() => guardar.mutate()} disabled={actual === '' || minimo === ''}>
            Guardar
          </Button>
        </>
      }
    >
      <div className="grid grid-cols-2 gap-3">
        <Field label={`Stock actual${esProducto ? '' : ` (${item.unidad_medida})`}`}>
          {(id) => (
            <Input id={id} type="number" min="0" step={esProducto ? '1' : '0.001'} value={actual} onChange={(e) => setActual(e.target.value)} />
          )}
        </Field>
        <Field label="Mínimo">
          {(id) => (
            <Input id={id} type="number" min="0" step={esProducto ? '1' : '0.001'} value={minimo} onChange={(e) => setMinimo(e.target.value)} />
          )}
        </Field>
      </div>
    </Modal>
  )
}
