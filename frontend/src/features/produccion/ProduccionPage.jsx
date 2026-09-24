import { useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, ChefHat, ClipboardList, Search, Wheat } from 'lucide-react'
import { Button } from '../../components/ui/Button'
import { Modal } from '../../components/ui/Modal'
import { Badge, EmptyState, ErrorState, PageHeader, Stepper } from '../../components/ui/misc'
import { PantallaCarga } from '../../components/ui/Spinner'
import { useToast } from '../../components/ui/toast'
import { mensajeError, post } from '../../lib/api'
import { fmtNumero } from '../../lib/format'
import { useMateriasPrimas, usePendienteProduccion, useProductos } from '../../lib/queries'
import { nivelStock } from '../../lib/stock'
import { MermaModal } from '../stock/MermaModal'

export default function ProduccionPage() {
  const qc = useQueryClient()
  const toast = useToast()
  const productosQ = useProductos()
  const pendiente = usePendienteProduccion()
  const insumos = useMateriasPrimas()
  const [cantidades, setCantidades] = useState({})
  const [busqueda, setBusqueda] = useState('')
  const [confirmar, setConfirmar] = useState(false)
  const [resultado, setResultado] = useState(null)
  const [merma, setMerma] = useState(false)

  const productos = useMemo(() => productosQ.data ?? [], [productosQ.data])
  const visibles = productos.filter((p) => p.nombre.toLowerCase().includes(busqueda.trim().toLowerCase()))
  const lotes = Object.entries(cantidades)
    .filter(([, c]) => c > 0)
    .map(([id, c]) => ({ producto: productos.find((p) => p.id === Number(id)), cantidad: c }))
    .filter((l) => l.producto)
  const unidades = lotes.reduce((t, l) => t + l.cantidad, 0)

  const registrar = useMutation({
    mutationFn: () =>
      post('/produccion', { lotes: lotes.map((l) => ({ producto_id: l.producto.id, cantidad: l.cantidad })) }),
    onSuccess: (r) => {
      setResultado(r)
      setCantidades({})
      setConfirmar(false)
      qc.invalidateQueries({ queryKey: ['productos'] })
      qc.invalidateQueries({ queryKey: ['materias-primas'] })
      qc.invalidateQueries({ queryKey: ['pendiente-produccion'] })
    },
    onError: (e) => {
      setConfirmar(false)
      toast.error(mensajeError(e))
    },
  })

  const cargarFaltantes = () => {
    const nuevas = { ...cantidades }
    for (const f of pendiente.data ?? []) if (f.faltante > 0) nuevas[f.producto_id] = f.faltante
    setCantidades(nuevas)
    toast.info('Cargamos las cantidades que faltan para cubrir los pedidos.')
  }

  if (productosQ.isLoading) return <PantallaCarga />
  if (productosQ.isError) return <ErrorState error={productosQ.error} onRetry={productosQ.refetch} />

  const faltantes = (pendiente.data ?? []).filter((f) => f.faltante > 0)

  return (
    <div className="pb-24">
      <PageHeader
        title="Producción"
        subtitle="Cargá lo que sale del horno. Los insumos se descuentan según la receta."
        actions={
          <Button variant="secondary" icon={AlertTriangle} onClick={() => setMerma(true)}>
            Merma
          </Button>
        }
      />

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[1fr_320px]">
        <div className="min-w-0 space-y-4">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3.5 top-1/2 h-5 w-5 -translate-y-1/2 text-stone-400" />
            <input
              className="input h-12 pl-11"
              placeholder="Buscar producto…"
              value={busqueda}
              onChange={(e) => setBusqueda(e.target.value)}
            />
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 2xl:grid-cols-3">
            {visibles.map((p) => {
              const c = cantidades[p.id] ?? 0
              return (
                <div
                  key={p.id}
                  className={`card flex items-center justify-between gap-3 p-3.5 ${c > 0 ? 'ring-2 ring-brand-400' : ''}`}
                >
                  <div className="min-w-0">
                    <p className="truncate font-semibold">{p.nombre}</p>
                    <p className="text-sm text-stone-500">
                      En mostrador: <span className="tabular font-semibold">{p.stock_mostrador}</span>
                    </p>
                  </div>
                  <Stepper value={c} onChange={(n) => setCantidades((x) => ({ ...x, [p.id]: n }))} size="lg" />
                </div>
              )
            })}
          </div>
        </div>

        <aside className="space-y-4">
          <section className="card p-4">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="flex items-center gap-2 font-bold">
                <ClipboardList className="h-5 w-5 text-brand-600" /> Para pedidos
              </h2>
              {faltantes.length > 0 && (
                <Button size="sm" variant="soft" onClick={cargarFaltantes}>
                  Cargar faltantes
                </Button>
              )}
            </div>
            {!pendiente.data?.length ? (
              <p className="text-sm text-stone-500">No hay pedidos pendientes.</p>
            ) : (
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-stone-500">
                  <tr>
                    <th className="pb-1 font-medium">Producto</th>
                    <th className="pb-1 text-right font-medium">Pedido</th>
                    <th className="pb-1 text-right font-medium">Falta</th>
                  </tr>
                </thead>
                <tbody className="tabular">
                  {pendiente.data.map((f) => (
                    <tr key={f.producto_id} className="border-t border-stone-100 dark:border-stone-800">
                      <td className="py-1.5">{f.nombre}</td>
                      <td className="py-1.5 text-right">{f.cantidad_pedida}</td>
                      <td className="py-1.5 text-right">
                        {f.faltante > 0 ? <Badge tone="red">{f.faltante}</Badge> : <Badge tone="green">OK</Badge>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          <section className="card p-4">
            <h2 className="mb-3 flex items-center gap-2 font-bold">
              <Wheat className="h-5 w-5 text-brand-600" /> Insumos
            </h2>
            {!insumos.data?.length ? (
              <p className="text-sm text-stone-500">Sin insumos cargados.</p>
            ) : (
              <ul className="space-y-2 text-sm">
                {insumos.data.map((m) => {
                  const n = nivelStock(m.stock_actual, m.stock_minimo)
                  return (
                    <li key={m.id} className="flex items-center justify-between gap-2">
                      <span className="truncate">{m.nombre}</span>
                      <Badge tone={n.tone}>
                        {fmtNumero(m.stock_actual)} {m.unidad_medida}
                      </Badge>
                    </li>
                  )
                })}
              </ul>
            )}
          </section>
        </aside>
      </div>

      {/* Barra de confirmación fija */}
      {unidades > 0 && (
        <div className="fixed inset-x-0 bottom-0 z-30 border-t border-stone-200 bg-white/95 p-3 backdrop-blur dark:border-stone-800 dark:bg-stone-900/95 lg:left-60">
          <div className="mx-auto flex max-w-5xl items-center justify-between gap-3">
            <p className="text-sm">
              <strong className="tabular text-lg">{unidades}</strong> unidades en {lotes.length} producto(s)
            </p>
            <div className="flex gap-2">
              <Button variant="ghost" onClick={() => setCantidades({})}>
                Limpiar
              </Button>
              <Button size="lg" icon={ChefHat} onClick={() => setConfirmar(true)}>
                Registrar horneada
              </Button>
            </div>
          </div>
        </div>
      )}

      <Modal
        open={confirmar}
        onClose={() => setConfirmar(false)}
        title="Confirmar producción"
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmar(false)}>
              Revisar
            </Button>
            <Button loading={registrar.isPending} onClick={() => registrar.mutate()}>
              Confirmar
            </Button>
          </>
        }
      >
        <ul className="divide-y divide-stone-100 dark:divide-stone-800">
          {lotes.map((l) => (
            <li key={l.producto.id} className="flex justify-between py-2">
              <span>{l.producto.nombre}</span>
              <span className="tabular font-bold">+{l.cantidad}</span>
            </li>
          ))}
        </ul>
      </Modal>

      <Modal
        open={!!resultado}
        onClose={() => setResultado(null)}
        size="sm"
        title="¡Producción registrada!"
        footer={<Button onClick={() => setResultado(null)}>Listo</Button>}
      >
        {resultado && (
          <div className="space-y-4">
            <p className="flex items-center gap-2 font-medium text-emerald-700 dark:text-emerald-400">
              <CheckCircle2 className="h-5 w-5" /> Se sumaron {resultado.unidades_totales} unidades al mostrador.
            </p>
            {resultado.insumos_consumidos.length > 0 ? (
              <div>
                <p className="label">Insumos descontados</p>
                <ul className="space-y-1 text-sm">
                  {resultado.insumos_consumidos.map((i) => (
                    <li key={i.materia_prima_id} className="flex justify-between">
                      <span>{i.nombre}</span>
                      <span className="tabular">
                        −{fmtNumero(i.cantidad)} {i.unidad_medida}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <EmptyState title="Sin receta cargada">
                Estos productos no tienen receta: no se descontaron insumos.
              </EmptyState>
            )}
          </div>
        )}
      </Modal>

      <MermaModal open={merma} onClose={() => setMerma(false)} productos={productos} />
    </div>
  )
}
