import { useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Building2, CalendarDays, Clock, MapPin, Pencil, Percent, Plus, Search, Trash2 } from 'lucide-react'
import { Button } from '../../components/ui/Button'
import { Field, Input, Select, Textarea } from '../../components/ui/Field'
import { Modal } from '../../components/ui/Modal'
import { Badge, EmptyState, ErrorState, Segmented, Stepper } from '../../components/ui/misc'
import { PantallaCarga } from '../../components/ui/Spinner'
import { useToast } from '../../components/ui/toast'
import { mensajeError, patch, post, put } from '../../lib/api'
import { fmtFecha } from '../../lib/format'
import { useClientes, useDescuentos, usePlantillas, useProductos, usePuntosEntrega } from '../../lib/queries'

const DIAS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
const hhmm = (t) => (t ? t.slice(0, 5) : '')

export default function PuntosEntregaPanel() {
  const [buscar, setBuscar] = useState('')
  const [inactivos, setInactivos] = useState(false)
  const [editando, setEditando] = useState(null) // null | 'nuevo' | punto
  const params = useMemo(() => ({ buscar: buscar.trim() || undefined, incluir_inactivos: inactivos || undefined }), [buscar, inactivos])
  const { data, isLoading, isError, error, refetch } = usePuntosEntrega(params)

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative min-w-[220px] max-w-md flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-stone-400" />
          <Input className="pl-9" placeholder="Buscar punto de entrega…" value={buscar} onChange={(e) => setBuscar(e.target.value)} />
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-sm font-medium">
          <input type="checkbox" className="h-4 w-4 accent-brand-600" checked={inactivos} onChange={(e) => setInactivos(e.target.checked)} />
          Ver inactivos
        </label>
        <Button className="ml-auto" icon={Plus} onClick={() => setEditando('nuevo')}>
          Nuevo punto
        </Button>
      </div>

      {isLoading ? (
        <PantallaCarga />
      ) : isError ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : !data.length ? (
        <div className="card">
          <EmptyState icon={Building2} title="Todavía no hay puntos de entrega">
            Cargá los locales y sucursales a los que se reparte: cada uno tiene su descuento, su pedido fijo y comparte la cuenta corriente del cliente.
          </EmptyState>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {data.map((p) => (
            <div key={p.id} className={`card flex flex-col p-4 ${p.activo ? '' : 'opacity-60'}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-bold">{p.nombre}</p>
                  <p className="truncate text-sm text-stone-500">{p.cliente_nombre}</p>
                </div>
                <Button size="icon-sm" variant="ghost" icon={Pencil} aria-label={`Editar ${p.nombre}`} onClick={() => setEditando(p)} />
              </div>
              <div className="mt-3 space-y-1 text-sm text-stone-600 dark:text-stone-400">
                {p.direccion && (
                  <p className="flex items-center gap-2">
                    <MapPin className="h-3.5 w-3.5 shrink-0" /> <span className="truncate">{p.direccion}</span>
                  </p>
                )}
                {p.ventana_desde && (
                  <p className="tabular flex items-center gap-2">
                    <Clock className="h-3.5 w-3.5" /> {hhmm(p.ventana_desde)} a {hhmm(p.ventana_hasta)}
                  </p>
                )}
              </div>
              <div className="mt-3 flex flex-wrap gap-1">
                {p.dias_entrega.length ? (
                  p.dias_entrega.map((d) => (
                    <Badge key={d} tone="brand">
                      {DIAS[d].slice(0, 3)}
                    </Badge>
                  ))
                ) : (
                  <span className="text-xs text-stone-400">Sin pedido fijo</span>
                )}
                {!p.activo && <Badge>Inactivo</Badge>}
              </div>
            </div>
          ))}
        </div>
      )}
      {editando && <PuntoModal punto={editando === 'nuevo' ? null : editando} onClose={() => setEditando(null)} />}
    </div>
  )
}

function PuntoModal({ punto, onClose }) {
  const [tab, setTab] = useState('datos')
  return (
    <Modal open onClose={onClose} size="lg" title={punto ? punto.nombre : 'Nuevo punto de entrega'} description={punto?.cliente_nombre}>
      {punto && (
        <Segmented
          className="mb-4"
          value={tab}
          onChange={setTab}
          options={[
            { value: 'datos', label: 'Datos' },
            { value: 'descuentos', label: 'Descuentos' },
            { value: 'pedido', label: 'Pedido fijo' },
          ]}
        />
      )}
      {tab === 'datos' && <DatosPunto punto={punto} onClose={onClose} />}
      {tab === 'descuentos' && punto && <Descuentos puntoId={punto.id} />}
      {tab === 'pedido' && punto && <PedidoFijo puntoId={punto.id} />}
    </Modal>
  )
}

function DatosPunto({ punto, onClose }) {
  const qc = useQueryClient()
  const toast = useToast()
  const { data: clientes = [] } = useClientes('')
  const [f, setF] = useState({
    cliente_id: punto?.cliente_id ?? '',
    nombre: punto?.nombre ?? '',
    direccion: punto?.direccion ?? '',
    latitud: punto?.latitud ?? '',
    longitud: punto?.longitud ?? '',
    ventana_desde: hhmm(punto?.ventana_desde),
    ventana_hasta: hhmm(punto?.ventana_hasta),
    contacto: punto?.contacto ?? '',
    notas: punto?.notas ?? '',
    activo: punto?.activo ?? true,
  })
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }))

  const guardar = useMutation({
    mutationFn: () => {
      const texto = (v) => (v === '' ? null : v.trim())
      const body = {
        nombre: f.nombre.trim(),
        direccion: texto(f.direccion),
        latitud: f.latitud === '' ? null : String(f.latitud),
        longitud: f.longitud === '' ? null : String(f.longitud),
        ventana_desde: f.ventana_desde || null,
        ventana_hasta: f.ventana_hasta || null,
        contacto: texto(f.contacto),
        notas: texto(f.notas),
      }
      return punto
        ? patch(`/contabilidad/puntos-entrega/${punto.id}`, { ...body, activo: f.activo })
        : post('/contabilidad/puntos-entrega', { ...body, cliente_id: Number(f.cliente_id) })
    },
    onSuccess: () => {
      toast.ok('Punto de entrega guardado.')
      qc.invalidateQueries({ queryKey: ['puntos-entrega'] })
      onClose()
    },
    onError: (e) => toast.error(mensajeError(e)),
  })
  const valido = f.nombre.trim() && (punto || f.cliente_id)

  return (
    <form
      className="grid grid-cols-1 gap-4 sm:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault()
        if (valido) guardar.mutate()
      }}
    >
      {!punto && (
        <Field label="Cliente" className="sm:col-span-2" hint="Todos los puntos de un cliente comparten su cuenta corriente.">
          {(id) => (
            <Select id={id} value={f.cliente_id} onChange={set('cliente_id')}>
              <option value="">Elegí un cliente…</option>
              {clientes.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.nombre}
                </option>
              ))}
            </Select>
          )}
        </Field>
      )}
      <Field label="Nombre del punto" className="sm:col-span-2">
        {(id) => <Input id={id} maxLength={120} autoFocus value={f.nombre} onChange={set('nombre')} />}
      </Field>
      <Field label="Dirección" className="sm:col-span-2">
        {(id) => <Input id={id} maxLength={200} value={f.direccion} onChange={set('direccion')} />}
      </Field>
      <Field label="Latitud" hint="Ej: -34.603722">
        {(id) => <Input id={id} type="number" step="0.000001" min="-90" max="90" value={f.latitud} onChange={set('latitud')} />}
      </Field>
      <Field label="Longitud" hint="Ej: -58.381592">
        {(id) => <Input id={id} type="number" step="0.000001" min="-180" max="180" value={f.longitud} onChange={set('longitud')} />}
      </Field>
      <Field label="Recibe desde">
        {(id) => <Input id={id} type="time" value={f.ventana_desde} onChange={set('ventana_desde')} />}
      </Field>
      <Field label="Recibe hasta">
        {(id) => <Input id={id} type="time" value={f.ventana_hasta} onChange={set('ventana_hasta')} />}
      </Field>
      <Field label="Contacto" className="sm:col-span-2">
        {(id) => <Input id={id} maxLength={120} placeholder="Nombre y teléfono de quien recibe" value={f.contacto} onChange={set('contacto')} />}
      </Field>
      <Field label="Notas" className="sm:col-span-2">
        {(id) => <Textarea id={id} maxLength={2000} placeholder="Timbre, horario de descarga, acceso…" value={f.notas} onChange={set('notas')} />}
      </Field>
      {punto && (
        <label className="flex cursor-pointer items-center gap-2 text-sm font-medium sm:col-span-2">
          <input type="checkbox" className="h-4 w-4 accent-brand-600" checked={f.activo} onChange={set('activo')} />
          Punto activo
        </label>
      )}
      <div className="flex justify-end gap-2 sm:col-span-2">
        <Button type="button" variant="secondary" onClick={onClose}>
          Cancelar
        </Button>
        <Button type="submit" loading={guardar.isPending} disabled={!valido}>
          Guardar
        </Button>
      </div>
    </form>
  )
}

// ---------- Descuentos ----------

function Descuentos({ puntoId }) {
  const qc = useQueryClient()
  const toast = useToast()
  const { data, isLoading, isError, error, refetch } = useDescuentos(puntoId)
  const { data: productos = [] } = useProductos()
  const [f, setF] = useState({ producto_id: '', porcentaje: '', motivo: '', desde: '', hasta: '' })
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }))

  const refrescar = () => qc.invalidateQueries({ queryKey: ['descuentos', puntoId] })
  const crear = useMutation({
    mutationFn: () =>
      post(`/contabilidad/puntos-entrega/${puntoId}/descuentos`, {
        producto_id: f.producto_id ? Number(f.producto_id) : null,
        porcentaje: String(f.porcentaje),
        motivo: f.motivo.trim(),
        vigente_desde: f.desde || null,
        vigente_hasta: f.hasta || null,
      }),
    onSuccess: () => {
      toast.ok('Descuento agregado.')
      setF({ producto_id: '', porcentaje: '', motivo: '', desde: '', hasta: '' })
      refrescar()
    },
    onError: (e) => toast.error(mensajeError(e)),
  })
  const alternar = useMutation({
    mutationFn: (d) => patch(`/contabilidad/puntos-entrega/${puntoId}/descuentos/${d.id}`, { activo: !d.activo }),
    onSuccess: refrescar,
    onError: (e) => toast.error(mensajeError(e)),
  })
  const valido = Number(f.porcentaje) > 0 && Number(f.porcentaje) <= 100 && f.motivo.trim()

  if (isLoading) return <PantallaCarga />
  if (isError) return <ErrorState error={error} onRetry={refetch} />

  return (
    <div className="space-y-5">
      <p className="text-sm text-stone-600 dark:text-stone-400">
        Para cada producto rige primero su descuento propio; si no tiene, el general del punto. No se suman entre sí. El precio queda
        fijado al confirmar la hoja de ruta.
      </p>
      {data.length === 0 ? (
        <p className="text-sm text-stone-500">Este punto no tiene descuentos.</p>
      ) : (
        <ul className="divide-y divide-stone-100 rounded-xl border border-stone-200 dark:divide-stone-800 dark:border-stone-800">
          {data.map((d) => (
            <li key={d.id} className={`flex flex-wrap items-center gap-3 px-3 py-2.5 ${d.activo ? '' : 'opacity-50'}`}>
              <Badge tone="brand">
                <Percent className="h-3 w-3" />
                {d.porcentaje}
              </Badge>
              <div className="min-w-0 flex-1">
                <p className="font-medium">{d.producto_nombre ?? 'Todos los productos'}</p>
                <p className="text-xs text-stone-500">
                  {d.motivo}
                  {(d.vigente_desde || d.vigente_hasta) &&
                    ` · ${d.vigente_desde ? fmtFecha(`${d.vigente_desde}T12:00:00`) : '…'} a ${d.vigente_hasta ? fmtFecha(`${d.vigente_hasta}T12:00:00`) : '…'}`}
                </p>
              </div>
              <Button size="sm" variant="ghost" loading={alternar.isPending && alternar.variables?.id === d.id} onClick={() => alternar.mutate(d)}>
                {d.activo ? 'Desactivar' : 'Activar'}
              </Button>
            </li>
          ))}
        </ul>
      )}

      <form
        className="grid grid-cols-1 gap-3 rounded-xl bg-stone-50 p-4 dark:bg-stone-950/40 sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault()
          if (valido) crear.mutate()
        }}
      >
        <p className="font-semibold sm:col-span-2">Agregar descuento</p>
        <Field label="Producto">
          {(id) => (
            <Select id={id} value={f.producto_id} onChange={set('producto_id')}>
              <option value="">Todos los productos</option>
              {productos.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.nombre}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label="Porcentaje">
          {(id) => <Input id={id} type="number" inputMode="decimal" min="0.01" max="100" step="0.01" placeholder="Ej: 20" value={f.porcentaje} onChange={set('porcentaje')} />}
        </Field>
        <Field label="Motivo" className="sm:col-span-2">
          {(id) => <Input id={id} maxLength={120} placeholder="Pan del día anterior, mayorista…" value={f.motivo} onChange={set('motivo')} />}
        </Field>
        <Field label="Vigente desde" hint="Opcional">
          {(id) => <Input id={id} type="date" value={f.desde} onChange={set('desde')} />}
        </Field>
        <Field label="Vigente hasta" hint="Opcional">
          {(id) => <Input id={id} type="date" value={f.hasta} onChange={set('hasta')} />}
        </Field>
        <div className="flex justify-end sm:col-span-2">
          <Button type="submit" icon={Plus} loading={crear.isPending} disabled={!valido}>
            Agregar
          </Button>
        </div>
      </form>
    </div>
  )
}

// ---------- Pedido fijo por día ----------

function PedidoFijo({ puntoId }) {
  const { data, isLoading, isError, error, refetch } = usePlantillas(puntoId)
  if (isLoading) return <PantallaCarga />
  if (isError) return <ErrorState error={error} onRetry={refetch} />
  // El editor arranca con lo guardado; se monta recién cuando los datos están listos
  return <EditorPedidoFijo puntoId={puntoId} inicial={data} />
}

function EditorPedidoFijo({ puntoId, inicial }) {
  const qc = useQueryClient()
  const toast = useToast()
  const { data: productos = [] } = useProductos()
  // { dia: { producto_id: cantidad } }
  const [plan, setPlan] = useState(() =>
    Object.fromEntries(inicial.map((d) => [d.dia_semana, Object.fromEntries(d.items.map((i) => [i.producto_id, i.cantidad]))])),
  )
  const [agregar, setAgregar] = useState({}) // producto elegido por día
  const porId = Object.fromEntries(productos.map((p) => [p.id, p]))

  const guardar = useMutation({
    mutationFn: () =>
      put(`/contabilidad/puntos-entrega/${puntoId}/plantillas`, {
        dias: Object.entries(plan)
          .filter(([, items]) => Object.keys(items).length > 0)
          .map(([dia, items]) => ({
            dia_semana: Number(dia),
            items: Object.entries(items).map(([producto_id, cantidad]) => ({ producto_id: Number(producto_id), cantidad })),
          })),
      }),
    onSuccess: (r) => {
      qc.setQueryData(['plantillas', puntoId], r)
      qc.invalidateQueries({ queryKey: ['puntos-entrega'] })
      toast.ok('Pedido fijo guardado.')
    },
    onError: (e) => toast.error(mensajeError(e)),
  })

  const cambiar = (dia, producto, cantidad) =>
    setPlan((p) => {
      const { [producto]: _, ...resto } = p[dia] ?? {}
      return { ...p, [dia]: cantidad > 0 ? { ...resto, [producto]: cantidad } : resto }
    })

  return (
    <div className="space-y-4">
      <p className="flex items-start gap-2 text-sm text-stone-600 dark:text-stone-400">
        <CalendarDays className="mt-0.5 h-4 w-4 shrink-0" />
        Lo que se le lleva cada día de la semana. Con esto se arman solas las hojas de ruta; los días sin productos no son días de entrega.
      </p>
      <div className="space-y-3">
        {DIAS.map((nombre, dia) => {
          const items = Object.entries(plan[dia] ?? {})
          return (
            <section key={dia} className="rounded-xl border border-stone-200 p-3 dark:border-stone-800">
              <h3 className="mb-2 flex items-center justify-between text-sm font-bold">
                {nombre}
                {items.length > 0 && <Badge tone="brand">{items.reduce((t, [, c]) => t + c, 0)} u</Badge>}
              </h3>
              {items.length > 0 && (
                <ul className="mb-2 space-y-1.5">
                  {items.map(([pid, cant]) => (
                    <li key={pid} className="flex items-center gap-3">
                      <span className="min-w-0 flex-1 truncate text-sm">{porId[pid]?.nombre ?? `Producto #${pid}`}</span>
                      <Stepper value={cant} min={0} max={100000} onChange={(n) => cambiar(dia, pid, n)} />
                      <Button size="icon-sm" variant="ghost" icon={Trash2} aria-label="Quitar" onClick={() => cambiar(dia, pid, 0)} />
                    </li>
                  ))}
                </ul>
              )}
              <div className="flex gap-2">
                <Select
                  aria-label={`Agregar producto el ${nombre}`}
                  value={agregar[dia] ?? ''}
                  onChange={(e) => setAgregar((a) => ({ ...a, [dia]: e.target.value }))}
                >
                  <option value="">Agregar producto…</option>
                  {productos
                    .filter((p) => !(plan[dia] ?? {})[p.id])
                    .map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.nombre}
                      </option>
                    ))}
                </Select>
                <Button
                  variant="secondary"
                  disabled={!agregar[dia]}
                  onClick={() => {
                    cambiar(dia, agregar[dia], 1)
                    setAgregar((a) => ({ ...a, [dia]: '' }))
                  }}
                >
                  Agregar
                </Button>
              </div>
            </section>
          )
        })}
      </div>
      <div className="flex justify-end">
        <Button loading={guardar.isPending} onClick={() => guardar.mutate()}>
          Guardar pedido fijo
        </Button>
      </div>
    </div>
  )
}
