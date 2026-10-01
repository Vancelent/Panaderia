import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeftRight,
  Banknote,
  BookUser,
  CreditCard,
  LockKeyhole,
  Plus,
  QrCode,
  Receipt,
  Split,
  Trash2,
} from 'lucide-react'
import { Button } from '../../components/ui/Button'
import { Field, Input, Select } from '../../components/ui/Field'
import { Modal } from '../../components/ui/Modal'
import { Badge, EmptyState } from '../../components/ui/misc'
import { Spinner } from '../../components/ui/Spinner'
import { useToast } from '../../components/ui/toast'
import { mensajeError, post } from '../../lib/api'
import { fmtDinero, fmtHora } from '../../lib/format'
import { qk, useClientes, useMediosPago, useVentasTurno } from '../../lib/queries'

const ICONOS = {
  Efectivo: Banknote,
  Tarjeta: CreditCard,
  Transferencia: ArrowLeftRight,
  QR: QrCode,
  'Cuenta corriente': BookUser,
}
const CUENTA_CORRIENTE = 'Cuenta corriente'
const MAX_PAGOS = 5

const aCentavos = (v) => Math.round((Number(v) || 0) * 100)
const aMonto = (centavos) => (centavos / 100).toFixed(2)

/** Montos típicos con los que paga el cliente, a partir del total. */
function sugerencias(total) {
  const billetes = [500, 1000, 2000, 5000, 10000, 20000]
  const res = new Set([Math.ceil(total)])
  for (const b of billetes) {
    const v = Math.ceil(total / b) * b
    if (v > total) res.add(v)
  }
  return [...res].sort((a, b) => a - b).slice(0, 4)
}

/** Buscador de clientes para la venta a cuenta corriente. */
function SelectorCliente({ value, onChange }) {
  const [buscar, setBuscar] = useState('')
  const { data: clientes = [] } = useClientes(value ? null : buscar)
  if (value) {
    return (
      <div className="flex items-center justify-between rounded-xl border border-brand-300 bg-brand-50 px-3 py-2.5 dark:border-brand-800 dark:bg-brand-950/40">
        <span className="font-semibold">{value.nombre}</span>
        <Button size="sm" variant="ghost" onClick={() => onChange(null)}>
          Cambiar
        </Button>
      </div>
    )
  }
  return (
    <div>
      <Input placeholder="Buscar cliente por nombre o teléfono…" value={buscar} onChange={(e) => setBuscar(e.target.value)} />
      <ul className="mt-2 max-h-36 overflow-y-auto rounded-xl border border-stone-200 dark:border-stone-800">
        {clientes.length === 0 ? (
          <li className="p-3 text-sm text-stone-500">Sin coincidencias. Podés darlo de alta en Clientes.</li>
        ) : (
          clientes.slice(0, 20).map((c) => (
            <li key={c.id}>
              <button
                type="button"
                onClick={() => onChange(c)}
                className="flex w-full justify-between px-3 py-2 text-left text-sm hover:bg-stone-50 dark:hover:bg-stone-800"
              >
                <span className="font-medium">{c.nombre}</span>
                <span className="tabular text-stone-500">{c.saldo_cuenta_corriente ? fmtDinero(c.saldo_cuenta_corriente) : ''}</span>
              </button>
            </li>
          ))
        )}
      </ul>
    </div>
  )
}

export function CobroModal({ open, onClose, items, total, onVendido }) {
  const qc = useQueryClient()
  const toast = useToast()
  const medios = useMediosPago()
  const [metodo, setMetodo] = useState('Efectivo')
  const [recibido, setRecibido] = useState('')
  const [dividido, setDividido] = useState(false)
  const [lineas, setLineas] = useState([{ metodo: 'Efectivo', monto: '' }])
  const [cliente, setCliente] = useState(null)

  const habilitados = medios.data?.habilitados ?? ['Efectivo', 'Transferencia', 'Tarjeta']
  const opciones = medios.data?.cuenta_corriente === false ? habilitados : [...habilitados, CUENTA_CORRIENTE]
  const totalCent = aCentavos(total)

  const usaCuentaCorriente = dividido ? lineas.some((l) => l.metodo === CUENTA_CORRIENTE) : metodo === CUENTA_CORRIENTE
  const sumaCent = lineas.reduce((t, l) => t + aCentavos(l.monto), 0)
  const restanteCent = totalCent - sumaCent

  const reset = () => {
    setRecibido('')
    setMetodo('Efectivo')
    setDividido(false)
    setLineas([{ metodo: 'Efectivo', monto: '' }])
    setCliente(null)
  }

  const vender = useMutation({
    mutationFn: () => {
      const body = { items: items.map((i) => ({ producto_id: i.producto.id, cantidad: i.cantidad })) }
      if (usaCuentaCorriente) body.cliente_id = cliente.id
      if (dividido) {
        // El servidor recalcula el total y rechaza pagos que no sumen (pagos_no_cuadran)
        body.pagos = lineas.map((l) => ({ metodo_pago: l.metodo, monto: aMonto(aCentavos(l.monto)) }))
      } else {
        body.metodo_pago = metodo
      }
      return post('/ventas', body)
    },
    onSuccess: (venta) => {
      const vuelto = !dividido && metodo === 'Efectivo' && recibido ? Number(recibido) - venta.monto : 0
      toast.ok(
        `Venta #${venta.id} registrada · ${fmtDinero(venta.monto)}` +
          (vuelto > 0 ? ` · Vuelto ${fmtDinero(vuelto)}` : ''),
      )
      qc.invalidateQueries({ queryKey: ['productos'] })
      qc.invalidateQueries({ queryKey: qk.ventasTurno })
      qc.invalidateQueries({ queryKey: ['saldos'] })
      reset()
      onVendido()
    },
    onError: (e) => {
      toast.error(mensajeError(e))
      // El stock pudo cambiar en otra caja: refrescamos la grilla
      qc.invalidateQueries({ queryKey: ['productos'] })
    },
  })

  const recibidoNum = Number(recibido) || 0
  const vuelto = recibidoNum - total
  const faltaEfectivo = !dividido && metodo === 'Efectivo' && recibido !== '' && vuelto < 0
  const lineasValidas = lineas.every((l) => aCentavos(l.monto) > 0)
  const bloqueado =
    faltaEfectivo ||
    (usaCuentaCorriente && !cliente) ||
    (dividido && (restanteCent !== 0 || !lineasValidas))

  const cambiarLinea = (idx, cambios) =>
    setLineas((ls) => ls.map((l, i) => (i === idx ? { ...l, ...cambios } : l)))
  const dividir = () => {
    setDividido(true)
    setLineas([{ metodo, monto: '' }])
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Cobrar"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Volver
          </Button>
          <Button variant="success" size="lg" loading={vender.isPending} disabled={bloqueado} onClick={() => vender.mutate()}>
            Confirmar {fmtDinero(total)}
          </Button>
        </>
      }
    >
      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (!bloqueado) vender.mutate()
        }}
      >
        <div className="mb-5 rounded-2xl bg-stone-100 p-4 text-center dark:bg-stone-800">
          <p className="text-sm text-stone-500">Total a cobrar</p>
          <p className="tabular text-4xl font-extrabold tracking-tight">{fmtDinero(total)}</p>
        </div>

        {!dividido ? (
          <>
            <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4" role="radiogroup" aria-label="Método de pago">
              {opciones.map((value) => {
                const Icon = ICONOS[value] ?? Banknote
                return (
                  <button
                    type="button"
                    key={value}
                    role="radio"
                    aria-checked={metodo === value}
                    onClick={() => setMetodo(value)}
                    className={`flex flex-col items-center gap-1.5 rounded-2xl border-2 p-3 text-sm font-semibold transition ${
                      metodo === value
                        ? 'border-brand-500 bg-brand-50 text-brand-800 dark:bg-brand-950/50 dark:text-brand-200'
                        : 'border-stone-200 hover:border-stone-300 dark:border-stone-700'
                    }`}
                  >
                    <Icon className="h-6 w-6" />
                    <span className="text-center leading-tight">{value}</span>
                  </button>
                )
              })}
            </div>
            <div className="mb-4 flex justify-end">
              <Button type="button" size="sm" variant="ghost" icon={Split} onClick={dividir}>
                Dividir el pago
              </Button>
            </div>
          </>
        ) : (
          <div className="mb-4 space-y-2">
            {lineas.map((l, idx) => (
              <div key={idx} className="flex items-center gap-2">
                <Select
                  aria-label={`Medio ${idx + 1}`}
                  className="w-40 shrink-0 sm:w-52"
                  value={l.metodo}
                  onChange={(e) => cambiarLinea(idx, { metodo: e.target.value })}
                >
                  {opciones.map((o) => (
                    <option key={o}>{o}</option>
                  ))}
                </Select>
                <Input
                  aria-label={`Monto ${idx + 1}`}
                  type="number"
                  inputMode="decimal"
                  min="0"
                  step="0.01"
                  className="tabular text-right font-bold"
                  placeholder="0,00"
                  value={l.monto}
                  onChange={(e) => cambiarLinea(idx, { monto: e.target.value })}
                />
                {restanteCent > 0 && idx === lineas.length - 1 && (
                  <Button
                    type="button"
                    size="sm"
                    variant="soft"
                    title="Completar con lo que falta"
                    onClick={() => cambiarLinea(idx, { monto: aMonto(aCentavos(l.monto) + restanteCent) })}
                  >
                    Resto
                  </Button>
                )}
                {lineas.length > 1 && (
                  <Button
                    type="button"
                    size="icon-sm"
                    variant="ghost"
                    icon={Trash2}
                    aria-label="Quitar medio"
                    onClick={() => setLineas((ls) => ls.filter((_, i) => i !== idx))}
                  />
                )}
              </div>
            ))}
            <div className="flex items-center justify-between">
              <Button
                type="button"
                size="sm"
                variant="secondary"
                icon={Plus}
                disabled={lineas.length >= MAX_PAGOS}
                onClick={() => setLineas((ls) => [...ls, { metodo: opciones[0], monto: '' }])}
              >
                Agregar medio
              </Button>
              <Button type="button" size="sm" variant="ghost" onClick={() => setDividido(false)}>
                Un solo medio
              </Button>
            </div>
            <div
              className={`flex items-center justify-between rounded-2xl p-4 ${
                restanteCent === 0
                  ? 'bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300'
                  : 'bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300'
              }`}
              role="status"
            >
              <span className="font-semibold">
                {restanteCent === 0 ? 'Pagos completos' : restanteCent > 0 ? 'Falta cubrir' : 'Sobra'}
              </span>
              <span className="tabular text-2xl font-extrabold">{fmtDinero(Math.abs(restanteCent) / 100)}</span>
            </div>
          </div>
        )}

        {usaCuentaCorriente && (
          <div className="mb-4">
            <p className="label">Cliente de la cuenta corriente</p>
            <SelectorCliente value={cliente} onChange={setCliente} />
          </div>
        )}

        {!dividido && metodo === 'Efectivo' && (
          <div className="space-y-3">
            <Field label="Paga con">
              {(id) => (
                <Input
                  id={id}
                  type="number"
                  inputMode="decimal"
                  min="0"
                  step="0.01"
                  className="tabular h-12 text-lg font-bold"
                  placeholder="Opcional, para calcular el vuelto"
                  value={recibido}
                  onChange={(e) => setRecibido(e.target.value)}
                />
              )}
            </Field>
            <div className="flex flex-wrap gap-2">
              {sugerencias(total).map((v) => (
                <Button key={v} type="button" variant="soft" size="sm" onClick={() => setRecibido(String(v))}>
                  {fmtDinero(v)}
                </Button>
              ))}
            </div>
            {recibido !== '' && (
              <div
                className={`flex items-center justify-between rounded-2xl p-4 ${
                  vuelto < 0
                    ? 'bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-300'
                    : 'bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300'
                }`}
              >
                <span className="font-semibold">{vuelto < 0 ? 'Falta' : 'Vuelto'}</span>
                <span className="tabular text-2xl font-extrabold">{fmtDinero(Math.abs(vuelto))}</span>
              </div>
            )}
          </div>
        )}
        <button type="submit" hidden />
      </form>
    </Modal>
  )
}

export function CierreModal({ open, onClose, carritoConItems }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [monto, setMonto] = useState('')
  const cerrar = useMutation({
    mutationFn: () => post('/turnos/actual/cierre', { monto_declarado: Number(monto) }),
    onSuccess: () => {
      toast.ok('Turno cerrado. ¡Gracias!')
      setMonto('')
      onClose()
      qc.setQueryData(qk.turnoActual, null)
      qc.removeQueries({ queryKey: qk.ventasTurno })
    },
    onError: (e) => toast.error(mensajeError(e)),
  })
  const valido = monto !== '' && Number(monto) >= 0

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="sm"
      title="Cerrar caja"
      description="Contá el efectivo del cajón e ingresá el total."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button variant="danger" icon={LockKeyhole} loading={cerrar.isPending} disabled={!valido} onClick={() => cerrar.mutate()}>
            Cerrar turno
          </Button>
        </>
      }
    >
      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (valido) cerrar.mutate()
        }}
        className="space-y-4"
      >
        {carritoConItems && (
          <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
            Hay productos en el ticket sin cobrar. Si cerrás, se descartan.
          </p>
        )}
        <Field label="Efectivo contado" hint="Incluí el fondo inicial. Tarjetas y transferencias no van.">
          {(id) => (
            <Input
              id={id}
              type="number"
              inputMode="decimal"
              step="0.01"
              min="0"
              className="tabular h-14 text-center text-2xl font-bold"
              value={monto}
              onChange={(e) => setMonto(e.target.value)}
            />
          )}
        </Field>
        <p className="text-xs text-stone-500">
          El sistema registra el arqueo y la encargada lo revisa. No se muestra la diferencia en caja.
        </p>
        <button type="submit" hidden />
      </form>
    </Modal>
  )
}

export function VentasTurnoModal({ open, onClose }) {
  const { data, isLoading } = useVentasTurno(open)
  return (
    <Modal open={open} onClose={onClose} title="Últimas ventas del turno">
      {isLoading ? (
        <div className="grid place-items-center py-10">
          <Spinner />
        </div>
      ) : !data?.length ? (
        <EmptyState icon={Receipt} title="Todavía no hay ventas en este turno" />
      ) : (
        <ul className="divide-y divide-stone-100 dark:divide-stone-800">
          {data.map((v) => (
            <li key={v.id} className="py-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-semibold">#{v.id}</span>
                  <span className="text-sm text-stone-500">{fmtHora(v.fecha)}</span>
                  {v.pagos.map((p, i) => (
                    <Badge key={i} tone={p.metodo_pago === 'Efectivo' ? 'green' : 'blue'}>
                      {p.metodo_pago}
                      {v.pagos.length > 1 ? ` ${fmtDinero(p.monto)}` : ''}
                    </Badge>
                  ))}
                </div>
                <span className="tabular font-bold">{fmtDinero(v.monto)}</span>
              </div>
              <p className="mt-1 text-sm text-stone-500">
                {v.detalles.map((d) => `${d.cantidad}× ${d.nombre}`).join(', ')}
              </p>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  )
}
