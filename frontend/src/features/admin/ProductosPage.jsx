import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { BookOpen, Pencil, Plus, Search, Trash2 } from 'lucide-react'
import { Button } from '../../components/ui/Button'
import { Field, Input, Select } from '../../components/ui/Field'
import { Modal } from '../../components/ui/Modal'
import { Badge, ErrorState, PageHeader } from '../../components/ui/misc'
import { PantallaCarga, Spinner } from '../../components/ui/Spinner'
import { useToast } from '../../components/ui/toast'
import { mensajeError, patch, post, put } from '../../lib/api'
import { fmtDinero, fmtNumero } from '../../lib/format'
import { useMateriasPrimas, useProductos, useReceta } from '../../lib/queries'

export default function ProductosPage() {
  const { data, isLoading, isError, error, refetch } = useProductos({ incluir_inactivos: true })
  const [editando, setEditando] = useState(null)
  const [receta, setReceta] = useState(null)
  const [busqueda, setBusqueda] = useState('')
  const filas = (data ?? []).filter((p) => p.nombre.toLowerCase().includes(busqueda.trim().toLowerCase()))

  return (
    <div>
      <PageHeader
        title="Productos"
        subtitle="Catálogo, precios y recetas (escandallo)."
        actions={
          <Button icon={Plus} onClick={() => setEditando('nuevo')}>
            Nuevo producto
          </Button>
        }
      />
      <div className="relative mb-4 max-w-md">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-stone-400" />
        <Input className="pl-9" placeholder="Buscar…" value={busqueda} onChange={(e) => setBusqueda(e.target.value)} />
      </div>
      {isLoading ? (
        <PantallaCarga />
      ) : isError ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead className="border-b border-stone-200 text-left text-xs uppercase tracking-wide text-stone-500 dark:border-stone-800">
              <tr>
                <th className="px-4 py-3 font-semibold">Producto</th>
                <th className="px-4 py-3 font-semibold">Categoría</th>
                <th className="px-4 py-3 text-right font-semibold">Precio</th>
                <th className="px-4 py-3 text-right font-semibold">Stock</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100 dark:divide-stone-800">
              {filas.map((p) => (
                <tr key={p.id} className={p.activo ? '' : 'opacity-50'}>
                  <td className="px-4 py-3 font-semibold">
                    {p.nombre} {!p.activo && <Badge className="ml-1">Inactivo</Badge>}
                  </td>
                  <td className="px-4 py-3 text-stone-500">{p.categoria ?? '—'}</td>
                  <td className="tabular px-4 py-3 text-right">{fmtDinero(p.precio_venta)}</td>
                  <td className="tabular px-4 py-3 text-right">{p.stock_mostrador}</td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-1">
                      <Button size="sm" variant="ghost" icon={BookOpen} onClick={() => setReceta(p)}>
                        Receta
                      </Button>
                      <Button size="icon-sm" variant="ghost" icon={Pencil} aria-label="Editar" onClick={() => setEditando(p)} />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {editando && (
        <ProductoModal
          producto={editando === 'nuevo' ? null : editando}
          categorias={[...new Set((data ?? []).map((p) => p.categoria).filter(Boolean))]}
          onClose={() => setEditando(null)}
        />
      )}
      {receta && <RecetaModal producto={receta} onClose={() => setReceta(null)} />}
    </div>
  )
}

function ProductoModal({ producto, categorias, onClose }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [f, setF] = useState({
    nombre: producto?.nombre ?? '',
    categoria: producto?.categoria ?? '',
    precio_venta: producto?.precio_venta ?? '',
    stock_minimo: producto?.stock_minimo ?? 0,
    stock_mostrador: 0,
    activo: producto?.activo ?? true,
  })
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }))
  const guardar = useMutation({
    mutationFn: () => {
      const base = {
        nombre: f.nombre.trim(),
        categoria: f.categoria.trim() || null,
        precio_venta: Number(f.precio_venta),
        stock_minimo: Number(f.stock_minimo) || 0,
      }
      return producto
        ? patch(`/productos/${producto.id}`, { ...base, activo: f.activo })
        : post('/productos', { ...base, stock_mostrador: Number(f.stock_mostrador) || 0 })
    },
    onSuccess: () => {
      toast.ok('Producto guardado.')
      qc.invalidateQueries({ queryKey: ['productos'] })
      onClose()
    },
    onError: (e) => toast.error(mensajeError(e)),
  })
  const valido = f.nombre.trim() && Number(f.precio_venta) > 0

  return (
    <Modal
      open
      onClose={onClose}
      title={producto ? 'Editar producto' : 'Nuevo producto'}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button loading={guardar.isPending} disabled={!valido} onClick={() => guardar.mutate()}>
            Guardar
          </Button>
        </>
      }
    >
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Nombre" className="sm:col-span-2">
          {(id) => <Input id={id} maxLength={120} value={f.nombre} onChange={set('nombre')} />}
        </Field>
        <Field label="Categoría" hint="Agrupa los botones en la caja.">
          {(id) => (
            <>
              <Input id={id} list="categorias" maxLength={60} value={f.categoria} onChange={set('categoria')} />
              <datalist id="categorias">
                {categorias.map((c) => (
                  <option key={c} value={c} />
                ))}
              </datalist>
            </>
          )}
        </Field>
        <Field label="Precio de venta">
          {(id) => <Input id={id} type="number" inputMode="decimal" min="0" step="0.01" value={f.precio_venta} onChange={set('precio_venta')} />}
        </Field>
        <Field label="Stock mínimo" hint="Por debajo aparece en rojo.">
          {(id) => <Input id={id} type="number" min="0" value={f.stock_minimo} onChange={set('stock_minimo')} />}
        </Field>
        {!producto && (
          <Field label="Stock inicial">
            {(id) => <Input id={id} type="number" min="0" value={f.stock_mostrador} onChange={set('stock_mostrador')} />}
          </Field>
        )}
        {producto && (
          <label className="flex cursor-pointer items-center gap-2 self-end pb-2.5 text-sm font-medium">
            <input type="checkbox" className="h-4 w-4 accent-brand-600" checked={f.activo} onChange={set('activo')} />
            Disponible para la venta
          </label>
        )}
      </div>
    </Modal>
  )
}

function RecetaModal({ producto, onClose }) {
  const qc = useQueryClient()
  const toast = useToast()
  const receta = useReceta(producto.id)
  const insumos = useMateriasPrimas()
  const [filas, setFilas] = useState(null) // null = sin editar todavía
  const actuales =
    filas ?? (receta.data?.insumos ?? []).map((i) => ({ materia_prima_id: i.materia_prima_id, cantidad: String(i.cantidad_necesaria) }))

  const porId = Object.fromEntries((insumos.data ?? []).map((m) => [m.id, m]))
  const costo = actuales.reduce(
    (t, f) => t + (Number(f.cantidad) || 0) * (porId[f.materia_prima_id]?.costo_unitario_actual ?? 0),
    0,
  )
  const margen = producto.precio_venta > 0 ? ((producto.precio_venta - costo) / producto.precio_venta) * 100 : 0

  const guardar = useMutation({
    mutationFn: () =>
      put(`/productos/${producto.id}/receta`, {
        insumos: actuales
          .filter((f) => f.materia_prima_id && Number(f.cantidad) > 0)
          .map((f) => ({ materia_prima_id: Number(f.materia_prima_id), cantidad_necesaria: f.cantidad })),
      }),
    onSuccess: (r) => {
      qc.setQueryData(['receta', producto.id], r)
      toast.ok('Receta guardada.')
      onClose()
    },
    onError: (e) => toast.error(mensajeError(e)),
  })
  const editar = (i, k, v) => setFilas(actuales.map((f, j) => (j === i ? { ...f, [k]: v } : f)))

  return (
    <Modal
      open
      onClose={onClose}
      size="lg"
      title={`Receta: ${producto.nombre}`}
      description="Cantidad de cada insumo para producir UNA unidad."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button loading={guardar.isPending} onClick={() => guardar.mutate()} disabled={filas === null}>
            Guardar receta
          </Button>
        </>
      }
    >
      {receta.isLoading || insumos.isLoading ? (
        <div className="grid place-items-center py-10">
          <Spinner />
        </div>
      ) : (
        <div className="space-y-4">
          {!insumos.data?.length && (
            <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
              Primero cargá insumos en Compras → Insumos.
            </p>
          )}
          {actuales.map((f, i) => (
            <div key={i} className="flex items-end gap-2">
              <Field label={i === 0 ? 'Insumo' : undefined} className="flex-1">
                {(id) => (
                  <Select id={id} value={f.materia_prima_id} onChange={(e) => editar(i, 'materia_prima_id', Number(e.target.value))}>
                    <option value="">Elegí…</option>
                    {(insumos.data ?? []).map((m) => (
                      <option key={m.id} value={m.id} disabled={actuales.some((x, j) => j !== i && x.materia_prima_id === m.id)}>
                        {m.nombre} ({m.unidad_medida})
                      </option>
                    ))}
                  </Select>
                )}
              </Field>
              <Field label={i === 0 ? 'Cantidad' : undefined} className="w-32">
                {(id) => <Input id={id} type="number" min="0" step="0.001" value={f.cantidad} onChange={(e) => editar(i, 'cantidad', e.target.value)} />}
              </Field>
              <span className="tabular w-24 pb-2.5 text-right text-sm text-stone-500">
                {fmtDinero((Number(f.cantidad) || 0) * (porId[f.materia_prima_id]?.costo_unitario_actual ?? 0))}
              </span>
              <Button size="icon" variant="ghost" icon={Trash2} aria-label="Quitar insumo" onClick={() => setFilas(actuales.filter((_, j) => j !== i))} />
            </div>
          ))}
          <Button variant="secondary" size="sm" icon={Plus} onClick={() => setFilas([...actuales, { materia_prima_id: '', cantidad: '' }])}>
            Agregar insumo
          </Button>
          <div className="grid grid-cols-3 gap-3 rounded-2xl bg-stone-100 p-4 text-center dark:bg-stone-800">
            <div>
              <p className="text-xs text-stone-500">Costo por unidad</p>
              <p className="tabular text-lg font-bold">{fmtDinero(costo)}</p>
            </div>
            <div>
              <p className="text-xs text-stone-500">Precio de venta</p>
              <p className="tabular text-lg font-bold">{fmtDinero(producto.precio_venta)}</p>
            </div>
            <div>
              <p className="text-xs text-stone-500">Margen</p>
              <p className={`tabular text-lg font-bold ${margen < 30 ? 'text-red-600' : 'text-emerald-700 dark:text-emerald-400'}`}>
                {fmtNumero(margen.toFixed(1))}%
              </p>
            </div>
          </div>
          <p className="text-xs text-stone-500">El costo usa el costo promedio ponderado de cada insumo según las compras registradas.</p>
        </div>
      )}
    </Modal>
  )
}
