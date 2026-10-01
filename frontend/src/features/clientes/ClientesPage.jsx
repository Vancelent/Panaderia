import { useDeferredValue, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Mail, MapPin, Pencil, Phone, Plus, Search, Users } from 'lucide-react'
import { Button } from '../../components/ui/Button'
import { Field, Input, Textarea } from '../../components/ui/Field'
import { Modal } from '../../components/ui/Modal'
import { Badge, EmptyState, ErrorState, PageHeader } from '../../components/ui/misc'
import { PantallaCarga, Spinner } from '../../components/ui/Spinner'
import { useToast } from '../../components/ui/toast'
import { mensajeError, patch, post } from '../../lib/api'
import { fmtDinero, fmtEntrega } from '../../lib/format'
import { useClientes, usePedidos } from '../../lib/queries'

export default function ClientesPage() {
  const [buscar, setBuscar] = useState('')
  const diferido = useDeferredValue(buscar.trim())
  const { data, isLoading, isError, error, refetch, isFetching } = useClientes(diferido)
  const [editando, setEditando] = useState(null) // null | 'nuevo' | cliente
  const [viendo, setViendo] = useState(null)

  return (
    <div>
      <PageHeader
        title="Clientes"
        subtitle="Clientes frecuentes y comercios para pedidos."
        actions={
          <Button icon={Plus} onClick={() => setEditando('nuevo')}>
            Nuevo cliente
          </Button>
        }
      />
      <div className="relative mb-4 max-w-md">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-stone-400" />
        <Input className="pl-9" placeholder="Buscar por nombre o teléfono…" value={buscar} onChange={(e) => setBuscar(e.target.value)} />
        {isFetching && <Spinner className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2" />}
      </div>

      {isLoading ? (
        <PantallaCarga />
      ) : isError ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : !data.length ? (
        <div className="card">
          <EmptyState icon={Users} title={diferido ? 'Sin coincidencias' : 'Todavía no hay clientes'} />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {data.map((c) => (
            <div key={c.id} className="card flex flex-col p-4">
              <div className="flex items-start justify-between gap-2">
                <button className="text-left font-bold hover:text-brand-700" onClick={() => setViendo(c)}>
                  {c.nombre}
                </button>
                <Button size="icon-sm" variant="ghost" icon={Pencil} aria-label="Editar" onClick={() => setEditando(c)} />
              </div>
              <div className="mt-2 space-y-1 text-sm text-stone-600 dark:text-stone-400">
                {Number(c.saldo_cuenta_corriente) !== 0 && (
                  <p className="tabular font-semibold">
                    Cuenta corriente: {fmtDinero(Math.abs(c.saldo_cuenta_corriente))}{' '}
                    <span className="text-xs">{c.saldo_cuenta_corriente > 0 ? 'debe' : 'a favor'}</span>
                  </p>
                )}
                {c.telefono && (
                  <a href={`tel:${c.telefono}`} className="flex items-center gap-2 hover:underline">
                    <Phone className="h-3.5 w-3.5" /> {c.telefono}
                  </a>
                )}
                {c.email && (
                  <p className="flex items-center gap-2">
                    <Mail className="h-3.5 w-3.5" /> {c.email}
                  </p>
                )}
                {c.direccion && (
                  <p className="flex items-center gap-2">
                    <MapPin className="h-3.5 w-3.5" /> {c.direccion}
                  </p>
                )}
              </div>
              {c.notas && <p className="mt-2 line-clamp-2 text-sm italic text-stone-500">{c.notas}</p>}
            </div>
          ))}
        </div>
      )}
      {editando && <ClienteModal cliente={editando === 'nuevo' ? null : editando} onClose={() => setEditando(null)} />}
      {viendo && <HistorialModal cliente={viendo} onClose={() => setViendo(null)} />}
    </div>
  )
}

function ClienteModal({ cliente, onClose }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [f, setF] = useState({
    nombre: cliente?.nombre ?? '',
    telefono: cliente?.telefono ?? '',
    cuit: cliente?.cuit ?? '',
    email: cliente?.email ?? '',
    direccion: cliente?.direccion ?? '',
    notas: cliente?.notas ?? '',
  })
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }))
  const guardar = useMutation({
    mutationFn: () => {
      const body = Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v.trim() || null]))
      return cliente ? patch(`/clientes/${cliente.id}`, body) : post('/clientes', body)
    },
    onSuccess: () => {
      toast.ok(cliente ? 'Cliente actualizado.' : 'Cliente creado.')
      qc.invalidateQueries({ queryKey: ['clientes'] })
      onClose()
    },
    onError: (e) => toast.error(mensajeError(e)),
  })
  return (
    <Modal
      open
      onClose={onClose}
      title={cliente ? 'Editar cliente' : 'Nuevo cliente'}
      footer={
        <>
          {cliente && (
            <Button
              variant="ghost"
              className="mr-auto text-red-600"
              onClick={() =>
                window.confirm('¿Dar de baja este cliente? Sus pedidos anteriores se conservan.') &&
                patch(`/clientes/${cliente.id}`, { activo: false }).then(() => {
                  qc.invalidateQueries({ queryKey: ['clientes'] })
                  onClose()
                }, (e) => toast.error(mensajeError(e)))
              }
            >
              Dar de baja
            </Button>
          )}
          <Button variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button loading={guardar.isPending} disabled={!f.nombre.trim()} onClick={() => guardar.mutate()}>
            Guardar
          </Button>
        </>
      }
    >
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Nombre" className="sm:col-span-2">
          {(id) => <Input id={id} maxLength={120} value={f.nombre} onChange={set('nombre')} />}
        </Field>
        <Field label="CUIT">
          {(id) => <Input id={id} maxLength={20} placeholder="30-12345678-9" value={f.cuit} onChange={set('cuit')} />}
        </Field>
        <Field label="Teléfono">
          {(id) => <Input id={id} type="tel" maxLength={40} value={f.telefono} onChange={set('telefono')} />}
        </Field>
        <Field label="Email">
          {(id) => <Input id={id} type="email" maxLength={120} value={f.email} onChange={set('email')} />}
        </Field>
        <Field label="Dirección" className="sm:col-span-2">
          {(id) => <Input id={id} maxLength={200} value={f.direccion} onChange={set('direccion')} />}
        </Field>
        <Field label="Notas" className="sm:col-span-2">
          {(id) => <Textarea id={id} maxLength={2000} value={f.notas} onChange={set('notas')} />}
        </Field>
      </div>
    </Modal>
  )
}

function HistorialModal({ cliente, onClose }) {
  const { data, isLoading } = usePedidos({ cliente_id: cliente.id })
  const tono = { Entregado: 'green', Cancelado: 'neutral', Listo: 'blue' }
  return (
    <Modal open onClose={onClose} title={cliente.nombre} description="Historial de pedidos">
      {isLoading ? (
        <PantallaCarga />
      ) : !data?.length ? (
        <EmptyState title="Sin pedidos todavía" />
      ) : (
        <ul className="divide-y divide-stone-100 dark:divide-stone-800">
          {[...data].reverse().map((p) => (
            <li key={p.id} className="flex items-center justify-between gap-3 py-2.5">
              <div>
                <p className="font-medium">
                  #{p.id} · {fmtEntrega(p.fecha_entrega)}
                </p>
                <p className="text-sm text-stone-500">{p.detalles.map((d) => `${d.cantidad}× ${d.nombre}`).join(', ')}</p>
              </div>
              <div className="text-right">
                <p className="tabular font-semibold">{fmtDinero(p.total)}</p>
                <Badge tone={tono[p.estado] ?? 'amber'}>{p.estado}</Badge>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  )
}
