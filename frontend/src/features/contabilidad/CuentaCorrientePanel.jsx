import { useDeferredValue, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { BookUser, FilePlus2, HandCoins, ReceiptText, Search } from 'lucide-react'
import { Button } from '../../components/ui/Button'
import { Field, Input, Select, Textarea } from '../../components/ui/Field'
import { Modal } from '../../components/ui/Modal'
import { Badge, EmptyState, ErrorState } from '../../components/ui/misc'
import { PantallaCarga } from '../../components/ui/Spinner'
import { useToast } from '../../components/ui/toast'
import { mensajeError, post } from '../../lib/api'
import { fmtDinero, fmtFechaHora } from '../../lib/format'
import { useClientes, useCuentaCorriente, useMediosPago, useSaldos } from '../../lib/queries'
import { nuevoUuid } from '../../lib/uuid'

const TONO_TIPO = { Cargo: 'amber', Pago: 'green', 'Nota de crédito': 'blue', Ajuste: 'violet' }

/** Saldo con su sentido: positivo = el cliente debe; negativo = saldo a favor. */
function Saldo({ valor, grande = false }) {
  const n = Number(valor)
  const color = n > 0 ? 'text-red-600 dark:text-red-400' : n < 0 ? 'text-emerald-700 dark:text-emerald-400' : ''
  return (
    <span className={`tabular font-extrabold ${grande ? 'text-3xl' : ''} ${color}`}>
      {fmtDinero(Math.abs(n))}
      {n !== 0 && <span className="ml-1 text-xs font-semibold">{n > 0 ? 'debe' : 'a favor'}</span>}
    </span>
  )
}

export default function CuentaCorrientePanel() {
  const [buscar, setBuscar] = useState('')
  const diferido = useDeferredValue(buscar.trim())
  const [clienteId, setClienteId] = useState(null)
  const saldos = useSaldos()
  const encontrados = useClientes(diferido || null)

  // Sin búsqueda: los clientes con cuenta corriente. Con búsqueda: cualquier cliente.
  const lista = diferido
    ? (encontrados.data ?? []).map((c) => ({ cliente_id: c.id, cliente: c.nombre, saldo: c.saldo_cuenta_corriente }))
    : (saldos.data ?? [])
  const cargando = diferido ? encontrados.isLoading : saldos.isLoading

  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,320px)_minmax(0,1fr)]">
      <section className="min-w-0">
        <div className="relative mb-3">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-stone-400" />
          <Input className="pl-9" placeholder="Buscar cliente…" value={buscar} onChange={(e) => setBuscar(e.target.value)} />
        </div>
        {cargando ? (
          <PantallaCarga />
        ) : saldos.isError && !diferido ? (
          <ErrorState error={saldos.error} onRetry={saldos.refetch} />
        ) : lista.length === 0 ? (
          <div className="card">
            <EmptyState icon={BookUser} title={diferido ? 'Sin coincidencias' : 'Todavía no hay cuentas corrientes'}>
              {diferido ? undefined : 'Aparecen acá los clientes que compran a cuenta o tienen movimientos.'}
            </EmptyState>
          </div>
        ) : (
          <ul className="card divide-y divide-stone-100 overflow-hidden dark:divide-stone-800">
            {lista.map((c) => (
              <li key={c.cliente_id}>
                <button
                  onClick={() => setClienteId(c.cliente_id)}
                  className={`flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition hover:bg-stone-50 dark:hover:bg-stone-800/50 ${
                    clienteId === c.cliente_id ? 'bg-brand-50 dark:bg-brand-950/40' : ''
                  }`}
                >
                  <span className="min-w-0 truncate font-semibold">{c.cliente}</span>
                  <Saldo valor={c.saldo} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="min-w-0">
        {clienteId ? (
          <Detalle key={clienteId} clienteId={clienteId} />
        ) : (
          <div className="card">
            <EmptyState icon={ReceiptText} title="Elegí un cliente">
              Vas a ver su saldo y todos sus movimientos.
            </EmptyState>
          </div>
        )}
      </section>
    </div>
  )
}

function Detalle({ clienteId }) {
  const { data, isLoading, isError, error, refetch } = useCuentaCorriente(clienteId)
  const [modal, setModal] = useState(null) // 'pago' | 'nota' | 'ajuste'

  if (isLoading) return <PantallaCarga />
  if (isError) return <ErrorState error={error} onRetry={refetch} />

  return (
    <div className="space-y-4">
      <div className="card flex flex-wrap items-center justify-between gap-4 p-5">
        <div>
          <h2 className="text-xl font-bold">{data.cliente}</h2>
          {data.cuit && <p className="tabular text-sm text-stone-500">CUIT {data.cuit}</p>}
          <p className="mt-2 text-sm text-stone-500">Saldo de la cuenta</p>
          <Saldo valor={data.saldo} grande />
        </div>
        <div className="flex flex-wrap gap-2">
          <Button icon={HandCoins} onClick={() => setModal('pago')}>
            Registrar pago
          </Button>
          <Button variant="secondary" icon={FilePlus2} onClick={() => setModal('nota')}>
            Nota de crédito
          </Button>
          <Button variant="ghost" onClick={() => setModal('ajuste')}>
            Ajuste
          </Button>
        </div>
      </div>

      {data.movimientos.length === 0 ? (
        <div className="card">
          <EmptyState icon={ReceiptText} title="Sin movimientos" />
        </div>
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full min-w-[560px] text-sm">
            <thead className="border-b border-stone-200 text-left text-xs uppercase tracking-wide text-stone-500 dark:border-stone-800">
              <tr>
                <th className="px-4 py-3 font-semibold">Fecha</th>
                <th className="px-4 py-3 font-semibold">Movimiento</th>
                <th className="px-4 py-3 font-semibold">Detalle</th>
                <th className="px-4 py-3 text-right font-semibold">Importe</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100 dark:divide-stone-800">
              {data.movimientos.map((m) => (
                <tr key={m.id}>
                  <td className="tabular whitespace-nowrap px-4 py-3 text-stone-500">{fmtFechaHora(m.fecha)}</td>
                  <td className="px-4 py-3">
                    <Badge tone={TONO_TIPO[m.tipo]}>{m.tipo}</Badge>
                    {m.metodo_pago && <span className="ml-2 text-stone-500">{m.metodo_pago}</span>}
                  </td>
                  <td className="px-4 py-3 text-stone-600 dark:text-stone-400">
                    {[m.observacion, m.referencia && `Ref. ${m.referencia}`, m.corrige_id && `Corrige #${m.corrige_id}`, m.usuario]
                      .filter(Boolean)
                      .join(' · ')}
                  </td>
                  <td
                    className={`tabular whitespace-nowrap px-4 py-3 text-right font-bold ${
                      m.importe > 0 ? 'text-red-600 dark:text-red-400' : 'text-emerald-700 dark:text-emerald-400'
                    }`}
                  >
                    {m.importe > 0 ? '+' : '−'} {fmtDinero(Math.abs(m.importe))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {modal === 'pago' && <PagoModal clienteId={clienteId} onClose={() => setModal(null)} />}
      {modal === 'nota' && <NotaCreditoModal clienteId={clienteId} onClose={() => setModal(null)} />}
      {modal === 'ajuste' && <AjusteModal clienteId={clienteId} movimientos={data.movimientos} onClose={() => setModal(null)} />}
    </div>
  )
}

/** Esqueleto común: mutación + invalidaciones + cierre. */
function useMovimiento(clienteId, ruta, onClose, textoOk) {
  const qc = useQueryClient()
  const toast = useToast()
  // La misma operación puede reenviarse (doble clic, reintento) sin duplicarse
  const [operacionId] = useState(nuevoUuid)
  return {
    operacionId,
    mutacion: useMutation({
      mutationFn: (cuerpo) => post(`/contabilidad/clientes/${clienteId}/${ruta}`, { ...cuerpo, operacion_id: operacionId }),
      onSuccess: () => {
        toast.ok(textoOk)
        qc.invalidateQueries({ queryKey: ['cuenta-corriente', clienteId] })
        qc.invalidateQueries({ queryKey: ['saldos'] })
        qc.invalidateQueries({ queryKey: ['clientes'] })
        qc.invalidateQueries({ queryKey: ['arqueos'] })
        onClose()
      },
      onError: (e) => toast.error(mensajeError(e)),
    }),
  }
}

function Pie({ onClose, mutacion, valido, texto }) {
  return (
    <>
      <Button variant="secondary" onClick={onClose}>
        Cancelar
      </Button>
      <Button loading={mutacion.isPending} disabled={!valido} type="submit" form="form-movimiento">
        {texto}
      </Button>
    </>
  )
}

function PagoModal({ clienteId, onClose }) {
  const medios = useMediosPago()
  const { mutacion } = useMovimiento(clienteId, 'pagos', onClose, 'Pago registrado.')
  const [monto, setMonto] = useState('')
  const [metodo, setMetodo] = useState('Efectivo')
  const [referencia, setReferencia] = useState('')
  const [obs, setObs] = useState('')
  const opciones = medios.data?.habilitados ?? ['Efectivo', 'Transferencia']
  const valido = Number(monto) > 0

  return (
    <Modal
      open
      onClose={onClose}
      size="sm"
      title="Registrar pago"
      footer={<Pie onClose={onClose} mutacion={mutacion} valido={valido} texto="Registrar" />}
    >
      <form
        id="form-movimiento"
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          if (valido)
            mutacion.mutate({
              monto: Number(monto).toFixed(2),
              metodo_pago: metodo,
              referencia: referencia.trim() || null,
              observacion: obs.trim() || null,
            })
        }}
      >
        <Field label="Monto cobrado">
          {(id) => <Input id={id} type="number" inputMode="decimal" min="0" step="0.01" autoFocus className="tabular h-12 text-lg font-bold" value={monto} onChange={(e) => setMonto(e.target.value)} />}
        </Field>
        <Field label="Medio" hint={metodo === 'Efectivo' ? 'El efectivo entra a tu turno de caja: necesitás tenerlo abierto.' : undefined}>
          {(id) => (
            <Select id={id} value={metodo} onChange={(e) => setMetodo(e.target.value)}>
              {opciones.map((o) => (
                <option key={o}>{o}</option>
              ))}
            </Select>
          )}
        </Field>
        {metodo !== 'Efectivo' && (
          <Field label="Referencia" hint="Nº de transferencia o de operación.">
            {(id) => <Input id={id} maxLength={120} value={referencia} onChange={(e) => setReferencia(e.target.value)} />}
          </Field>
        )}
        <Field label="Observación">
          {(id) => <Input id={id} maxLength={200} value={obs} onChange={(e) => setObs(e.target.value)} />}
        </Field>
      </form>
    </Modal>
  )
}

function NotaCreditoModal({ clienteId, onClose }) {
  const { mutacion } = useMovimiento(clienteId, 'notas-credito', onClose, 'Nota de crédito registrada.')
  const [monto, setMonto] = useState('')
  const [obs, setObs] = useState('')
  const valido = Number(monto) > 0 && obs.trim().length > 0

  return (
    <Modal
      open
      onClose={onClose}
      size="sm"
      title="Nota de crédito"
      description="Reduce la deuda (por ejemplo, mercadería devuelta). No mueve efectivo ni stock."
      footer={<Pie onClose={onClose} mutacion={mutacion} valido={valido} texto="Registrar" />}
    >
      <form
        id="form-movimiento"
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          if (valido) mutacion.mutate({ monto: Number(monto).toFixed(2), observacion: obs.trim() })
        }}
      >
        <Field label="Importe a descontar">
          {(id) => <Input id={id} type="number" inputMode="decimal" min="0" step="0.01" autoFocus className="tabular h-12 text-lg font-bold" value={monto} onChange={(e) => setMonto(e.target.value)} />}
        </Field>
        <Field label="Motivo" hint="Obligatorio: queda registrado.">
          {(id) => <Textarea id={id} maxLength={200} value={obs} onChange={(e) => setObs(e.target.value)} />}
        </Field>
      </form>
    </Modal>
  )
}

function AjusteModal({ clienteId, movimientos, onClose }) {
  const { mutacion } = useMovimiento(clienteId, 'ajustes', onClose, 'Ajuste registrado.')
  const [importe, setImporte] = useState('')
  const [obs, setObs] = useState('')
  const [corrige, setCorrige] = useState('')
  const valido = Number(importe) !== 0 && obs.trim().length > 0

  return (
    <Modal
      open
      onClose={onClose}
      size="sm"
      title="Ajuste"
      description="Corrige un error con un movimiento nuevo. El original no se modifica ni se borra."
      footer={<Pie onClose={onClose} mutacion={mutacion} valido={valido} texto="Registrar" />}
    >
      <form
        id="form-movimiento"
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          if (valido)
            mutacion.mutate({
              importe: Number(importe).toFixed(2),
              observacion: obs.trim(),
              corrige_id: corrige ? Number(corrige) : null,
            })
        }}
      >
        <Field label="Importe" hint="Positivo aumenta la deuda; negativo la reduce.">
          {(id) => <Input id={id} type="number" inputMode="decimal" step="0.01" autoFocus className="tabular h-12 text-lg font-bold" value={importe} onChange={(e) => setImporte(e.target.value)} />}
        </Field>
        <Field label="Movimiento que corrige" hint="Opcional.">
          {(id) => (
            <Select id={id} value={corrige} onChange={(e) => setCorrige(e.target.value)}>
              <option value="">Ninguno</option>
              {movimientos.slice(0, 30).map((m) => (
                <option key={m.id} value={m.id}>
                  #{m.id} · {m.tipo} · {fmtDinero(m.importe)}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label="Motivo" hint="Obligatorio: queda registrado.">
          {(id) => <Textarea id={id} maxLength={200} value={obs} onChange={(e) => setObs(e.target.value)} />}
        </Field>
      </form>
    </Modal>
  )
}
