import { useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  ArrowRight,
  Ban,
  ClipboardList,
  HandCoins,
  Pencil,
  Phone,
  Plus,
  StickyNote,
} from 'lucide-react'
import { useAuth } from '../../auth/context'
import { Button } from '../../components/ui/Button'
import { Modal } from '../../components/ui/Modal'
import { Badge, EmptyState, ErrorState, PageHeader, Segmented } from '../../components/ui/misc'
import { PantallaCarga } from '../../components/ui/Spinner'
import { useToast } from '../../components/ui/toast'
import { mensajeError, post } from '../../lib/api'
import { fmtDinero, fmtEntrega, isoLocal, sumarDias } from '../../lib/format'
import { usePedidos } from '../../lib/queries'
import { puedeCobrar, ROL } from '../../lib/roles'
import { PedidoFormModal } from './PedidoFormModal'

const COLUMNAS = [
  { estado: 'Pendiente', titulo: 'Pendientes', punto: 'bg-amber-500' },
  { estado: 'En preparación', titulo: 'En el horno', punto: 'bg-brand-500' },
  { estado: 'Listo', titulo: 'Listos para entregar', punto: 'bg-emerald-500' },
]
const SIGUIENTE = { Pendiente: 'En preparación', 'En preparación': 'Listo' }
const ANTERIOR = { 'En preparación': 'Pendiente', Listo: 'En preparación' }

function rango(filtro) {
  const hoy = new Date()
  if (filtro === 'hoy') return { desde: isoLocal(hoy), hasta: isoLocal(hoy) }
  if (filtro === 'manana') {
    const m = sumarDias(hoy, 1)
    return { desde: isoLocal(m), hasta: isoLocal(m) }
  }
  return undefined
}

export default function PedidosPage() {
  const { user } = useAuth()
  const [filtro, setFiltro] = useState('todos')
  const [editando, setEditando] = useState(null) // null | 'nuevo' | pedido
  const [entregando, setEntregando] = useState(null)
  const params = useMemo(() => rango(filtro), [filtro])
  const { data, isLoading, isError, error, refetch } = usePedidos(params)
  const cobra = puedeCobrar(user)

  const porEstado = useMemo(() => {
    const g = Object.fromEntries(COLUMNAS.map((c) => [c.estado, []]))
    for (const p of data ?? []) g[p.estado]?.push(p)
    return g
  }, [data])

  return (
    <div>
      <PageHeader
        title="Pedidos"
        subtitle="Encargos y comandas. Se actualiza solo cada 15 segundos."
        actions={
          cobra && (
            <Button icon={Plus} onClick={() => setEditando('nuevo')}>
              Nuevo pedido
            </Button>
          )
        }
      />
      <Segmented
        className="mb-4"
        value={filtro}
        onChange={setFiltro}
        options={[
          { value: 'todos', label: 'Todos' },
          { value: 'hoy', label: 'Hoy' },
          { value: 'manana', label: 'Mañana' },
        ]}
      />

      {isLoading ? (
        <PantallaCarga />
      ) : isError ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          {COLUMNAS.map((col) => (
            <section key={col.estado} className="flex min-h-[200px] min-w-0 flex-col rounded-2xl bg-stone-200/50 p-3 dark:bg-stone-900/60">
              <header className="mb-3 flex items-center gap-2 px-1">
                <span className={`h-2.5 w-2.5 rounded-full ${col.punto}`} />
                <h2 className="font-bold">{col.titulo}</h2>
                <span className="ml-auto rounded-full bg-white px-2 text-sm font-semibold text-stone-600 dark:bg-stone-800 dark:text-stone-300">
                  {porEstado[col.estado].length}
                </span>
              </header>
              <div className="flex flex-1 flex-col gap-3">
                {porEstado[col.estado].length === 0 ? (
                  <EmptyState icon={ClipboardList} title="Nada por acá" />
                ) : (
                  porEstado[col.estado].map((p) => (
                    <TarjetaPedido
                      key={p.id}
                      pedido={p}
                      user={user}
                      onEditar={() => setEditando(p)}
                      onEntregar={() => setEntregando(p)}
                    />
                  ))
                )}
              </div>
            </section>
          ))}
        </div>
      )}

      {editando && (
        <PedidoFormModal
          pedido={editando === 'nuevo' ? null : editando}
          onClose={() => setEditando(null)}
        />
      )}
      <EntregaModal pedido={entregando} onClose={() => setEntregando(null)} />
    </div>
  )
}

function TarjetaPedido({ pedido: p, user, onEditar, onEntregar }) {
  const qc = useQueryClient()
  const toast = useToast()
  const mover = useMutation({
    mutationFn: (estado) => post(`/pedidos/${p.id}/estado`, { estado }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['pedidos'] })
      qc.invalidateQueries({ queryKey: ['pendiente-produccion'] })
      if (r.estado === 'Cancelado') toast.info(`Pedido #${p.id} cancelado.`)
    },
    onError: (e) => toast.error(mensajeError(e)),
  })
  const atrasado = new Date(p.fecha_entrega) < new Date()
  const cobra = puedeCobrar(user)

  return (
    <article className="card animate-fade-in p-3.5">
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-bold" title={p.cliente_nombre || p.contacto}>{p.cliente_nombre || p.contacto}</p>
          <p className="text-xs text-stone-500">Pedido #{p.id}</p>
        </div>
        <Badge tone={atrasado ? 'red' : 'neutral'}>{fmtEntrega(p.fecha_entrega)}</Badge>
      </div>
      <ul className="mb-2 space-y-0.5 text-sm">
        {p.detalles.map((d) => (
          <li key={d.producto_id} className="flex gap-2">
            <span className="tabular w-8 shrink-0 text-right font-bold text-brand-700 dark:text-brand-300">{d.cantidad}×</span>
            <span className="truncate">{d.nombre}</span>
          </li>
        ))}
      </ul>
      {p.notas && (
        <p className="mb-2 flex gap-1.5 rounded-lg bg-amber-50 p-2 text-sm text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
          <StickyNote className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          {p.notas}
        </p>
      )}
      <div className="flex items-center justify-between gap-2 border-t border-stone-100 pt-2.5 dark:border-stone-800">
        <span className="tabular font-bold">{fmtDinero(p.total)}</span>
        <div className="flex gap-1">
          {cobra && p.estado === 'Pendiente' && (
            <Button size="icon-sm" variant="ghost" icon={Pencil} onClick={onEditar} aria-label="Editar pedido" title="Editar" />
          )}
          {user.rol !== ROL.PANADERO && (
            <Button
              size="icon-sm"
              variant="ghost"
              icon={Ban}
              aria-label="Cancelar pedido"
              title="Cancelar pedido"
              onClick={() => window.confirm(`¿Cancelar el pedido #${p.id}?`) && mover.mutate('Cancelado')}
            />
          )}
          {ANTERIOR[p.estado] && (
            <Button size="icon-sm" variant="secondary" icon={ArrowLeft} loading={mover.isPending && mover.variables === ANTERIOR[p.estado]} onClick={() => mover.mutate(ANTERIOR[p.estado])} aria-label={`Volver a ${ANTERIOR[p.estado]}`} title={`Volver a ${ANTERIOR[p.estado]}`} />
          )}
          {SIGUIENTE[p.estado] && (
            <Button size="sm" variant="soft" loading={mover.isPending && mover.variables === SIGUIENTE[p.estado]} onClick={() => mover.mutate(SIGUIENTE[p.estado])}>
              {p.estado === 'Pendiente' ? 'Al horno' : 'Listo'}
              <ArrowRight className="h-4 w-4" />
            </Button>
          )}
          {p.estado === 'Listo' && cobra && (
            <Button size="sm" variant="success" icon={HandCoins} onClick={onEntregar}>
              Entregar
            </Button>
          )}
        </div>
      </div>
    </article>
  )
}

function EntregaModal({ pedido, onClose }) {
  const qc = useQueryClient()
  const toast = useToast()
  const entregar = useMutation({
    mutationFn: (metodo_pago) => post(`/pedidos/${pedido.id}/entrega`, { metodo_pago }),
    onSuccess: () => {
      toast.ok(`Pedido #${pedido.id} entregado y cobrado.`)
      qc.invalidateQueries({ queryKey: ['pedidos'] })
      qc.invalidateQueries({ queryKey: ['productos'] })
      qc.invalidateQueries({ queryKey: ['ventas-turno'] })
      onClose()
    },
    onError: (e) => toast.error(mensajeError(e)),
  })
  if (!pedido) return null
  return (
    <Modal open onClose={onClose} size="sm" title={`Entregar pedido #${pedido.id}`} description={pedido.cliente_nombre || pedido.contacto}>
      <div className="mb-4 rounded-2xl bg-stone-100 p-4 text-center dark:bg-stone-800">
        <p className="text-sm text-stone-500">A cobrar</p>
        <p className="tabular text-3xl font-extrabold">{fmtDinero(pedido.total)}</p>
      </div>
      {pedido.cliente_nombre == null && pedido.contacto && (
        <p className="mb-3 flex items-center gap-2 text-sm text-stone-500">
          <Phone className="h-4 w-4" /> Pedido sin cliente registrado
        </p>
      )}
      <p className="mb-2 text-sm font-medium">¿Cómo paga?</p>
      <div className="grid gap-2">
        {['Efectivo', 'Tarjeta', 'Transferencia'].map((m) => (
          <Button
            key={m}
            variant="secondary"
            size="lg"
            loading={entregar.isPending && entregar.variables === m}
            disabled={entregar.isPending}
            onClick={() => entregar.mutate(m)}
          >
            {m}
          </Button>
        ))}
      </div>
      <p className="mt-3 text-xs text-stone-500">Se registra en tu turno de caja y descuenta el stock del mostrador.</p>
    </Modal>
  )
}
