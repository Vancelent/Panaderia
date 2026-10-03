import { useEffect, useMemo, useReducer, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeftRight, Banknote, BookUser, CreditCard, QrCode, Trash2 } from 'lucide-react'
import { cobro } from '@panaderia/core'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Field'
import { Modal } from '../../components/ui/Modal'
import { useToast } from '../../components/ui/toast'
import { mensajeError, post } from '../../lib/api'
import { fmtDinero } from '../../lib/format'
import { qk, useClientes, useMediosPago } from '../../lib/queries'

const ICONOS = {
  Efectivo: Banknote,
  Tarjeta: CreditCard,
  Transferencia: ArrowLeftRight,
  QR: QrCode,
  'Cuenta corriente': BookUser,
}
const MEDIOS_POR_DEFECTO = ['Efectivo', 'Transferencia', 'Tarjeta']
const EN_CAMPO = ['INPUT', 'TEXTAREA', 'SELECT']

const aPesos = (centavos) => centavos / 100

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

/**
 * Cobro. Se maneja entero con el teclado (docs/rfc-001 §6.2):
 *   1…5 elige el medio · número + Enter fija el monto · Tab agrega otro medio por lo que falta (pago
 *   mixto) · si cubre el total con vuelto, lo muestra y Enter confirma.
 * La lógica es la del controlador compartido (packages/core); acá solo se dibuja y se leen las teclas.
 */
export function CobroModal({ open, onClose, items, totalCentavos, onVendido }) {
  const qc = useQueryClient()
  const toast = useToast()
  const medios = useMediosPago()
  const opciones = useMemo(() => {
    const habilitados = medios.data?.habilitados ?? MEDIOS_POR_DEFECTO
    return medios.data?.cuenta_corriente === false ? habilitados : [...habilitados, cobro.CUENTA_CORRIENTE]
  }, [medios.data])
  const [c, despachar] = useReducer(cobro.reducir, undefined, () => cobro.abrir({ totalCentavos, opciones }))
  const [cliente, setCliente] = useState(null)
  const cuerpo = useRef(null)
  const campo = useRef(null)
  const enviado = useRef(false)

  useEffect(() => {
    despachar({ tipo: 'opciones', opciones })
  }, [opciones])

  const completo = cobro.completo(c)
  const listo = cobro.listoParaConfirmar(c)
  const vuelto = cobro.vueltoCentavos(c)
  const necesitaCliente = cobro.requiereCliente(c) || c.medio === cobro.CUENTA_CORRIENTE

  const vender = useMutation({
    mutationFn: () => post('/ventas', { items, ...cobro.cuerpoDePagos(c) }),
    onSuccess: (venta) => {
      toast.ok(
        `Venta #${venta.id} registrada · ${fmtDinero(venta.monto)}` +
          (vuelto > 0 ? ` · Vuelto ${fmtDinero(aPesos(vuelto))}` : ''),
      )
      qc.invalidateQueries({ queryKey: ['productos'] })
      qc.invalidateQueries({ queryKey: qk.ventasTurno })
      qc.invalidateQueries({ queryKey: ['saldos'] })
      onVendido()
    },
    onError: (e) => {
      enviado.current = false
      toast.error(mensajeError(e))
      // El stock pudo cambiar en otra caja: refrescamos la grilla
      qc.invalidateQueries({ queryKey: ['productos'] })
    },
  })

  const confirmarVenta = () => {
    if (!listo || enviado.current) return
    enviado.current = true
    vender.mutate()
  }

  // Si el pago cubre el total justo (sin vuelto que mostrar ni cliente que elegir), se confirma solo
  useEffect(() => {
    if (listo && vuelto === 0 && !cobro.requiereCliente(c)) confirmarVenta()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listo, vuelto])

  // Con el pago completo el foco pasa al cuerpo del cobro, así Enter confirma la venta
  useEffect(() => {
    if (completo) cuerpo.current?.focus()
  }, [completo])

  const teclas = (e) => {
    if (e.target === campo.current) {
      if (e.key === 'Enter') {
        e.preventDefault()
        despachar({ tipo: 'confirmar' })
      } else if (e.key === 'Tab' && !e.shiftKey) {
        // Tab después de un monto parcial: otro medio por lo que falta
        e.preventDefault()
        despachar({ tipo: 'agregar_medio' })
        cuerpo.current?.focus()
      }
      return
    }
    if (EN_CAMPO.includes(e.target.tagName)) return // el buscador de clientes, etc.
    if (/^[1-5]$/.test(e.key)) {
      e.preventDefault()
      despachar({ tipo: 'medio', indice: Number(e.key) })
      campo.current?.focus()
    } else if (e.key === 'Enter' && e.target === cuerpo.current) {
      e.preventDefault()
      if (listo) confirmarVenta()
      else despachar({ tipo: 'confirmar' })
    }
  }

  const previo = cobro.vueltoPrevio(c)
  const restante = cobro.restante(c)

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
          <Button variant="success" size="lg" loading={vender.isPending} disabled={!listo} onClick={confirmarVenta}>
            Confirmar {fmtDinero(aPesos(c.total))}
          </Button>
        </>
      }
    >
      <div ref={cuerpo} tabIndex={-1} data-autofocus onKeyDown={teclas} className="space-y-4 outline-none">
        <div className="rounded-2xl bg-stone-100 p-4 text-center dark:bg-stone-800" aria-live="polite">
          <p className="text-sm text-stone-500">{c.pagos.length ? 'Falta cobrar' : 'Total a cobrar'}</p>
          <p className="tabular text-4xl font-extrabold tracking-tight">{fmtDinero(aPesos(restante || (completo ? 0 : c.total)))}</p>
          {c.pagos.length > 0 && <p className="tabular mt-1 text-xs text-stone-500">Total de la venta {fmtDinero(aPesos(c.total))}</p>}
        </div>

        {!completo && (
          <>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-5" role="radiogroup" aria-label="Medio de pago">
              {c.opciones.map((value, i) => {
                const Icon = ICONOS[value] ?? Banknote
                return (
                  <button
                    type="button"
                    key={value}
                    role="radio"
                    aria-checked={c.medio === value}
                    onClick={() => {
                      despachar({ tipo: 'medio', metodo: value })
                      campo.current?.focus()
                    }}
                    className={`relative flex flex-col items-center gap-1.5 rounded-2xl border-2 p-3 text-sm font-semibold transition ${
                      c.medio === value
                        ? 'border-brand-500 bg-brand-50 text-brand-800 dark:bg-brand-950/50 dark:text-brand-200'
                        : 'border-stone-200 hover:border-stone-300 dark:border-stone-700'
                    }`}
                  >
                    <kbd className="absolute left-2 top-1.5 rounded bg-stone-200 px-1 text-[10px] font-bold text-stone-600 dark:bg-stone-700 dark:text-stone-300">
                      {i + 1}
                    </kbd>
                    <Icon className="h-6 w-6" />
                    <span className="text-center leading-tight">{value}</span>
                  </button>
                )
              })}
            </div>

            <div className="flex items-center gap-2">
              <Input
                ref={campo}
                aria-label={`Monto en ${c.medio}`}
                inputMode="decimal"
                autoComplete="off"
                className="tabular h-12 text-right text-lg font-bold"
                placeholder={`${fmtDinero(aPesos(restante))} (Enter cobra todo)`}
                value={c.buffer}
                onChange={(e) => despachar({ tipo: 'escribir', texto: e.target.value })}
              />
              <Button type="button" variant="soft" onClick={() => despachar({ tipo: 'confirmar' })}>
                Cobrar
              </Button>
            </div>
            <p className="text-xs text-stone-500">
              <kbd className="font-bold">1</kbd>–<kbd className="font-bold">5</kbd> medio · <kbd className="font-bold">Enter</kbd> confirma el monto ·{' '}
              <kbd className="font-bold">Tab</kbd> suma otro medio por lo que falta
            </p>
            {previo > 0 && (
              <div className="flex items-center justify-between rounded-2xl bg-emerald-50 p-3 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300">
                <span className="font-semibold">Vuelto</span>
                <span className="tabular text-2xl font-extrabold">{fmtDinero(aPesos(previo))}</span>
              </div>
            )}
          </>
        )}

        {c.aviso && (
          <p role="alert" className="rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
            {c.aviso.tipo === 'excede_total' && `Ese medio no da vuelto: el monto no puede superar lo que falta (${fmtDinero(aPesos(c.aviso.falta))}).`}
            {c.aviso.tipo === 'monto_invalido' && 'Ingresá un monto válido.'}
            {c.aviso.tipo === 'max_pagos' && `Se pueden usar hasta ${cobro.MAX_PAGOS} medios: el último tiene que cubrir lo que falta.`}
          </p>
        )}

        {c.pagos.length > 0 && (
          <ul className="divide-y divide-stone-100 rounded-2xl border border-stone-200 dark:divide-stone-800 dark:border-stone-800">
            {c.pagos.map((p, i) => (
              <li key={i} className="flex items-center justify-between gap-3 px-3 py-2">
                <span className="font-semibold">{p.metodo}</span>
                <span className="flex items-center gap-2">
                  <span className="tabular font-bold">{fmtDinero(aPesos(p.centavos))}</span>
                  <Button type="button" size="icon-sm" variant="ghost" icon={Trash2} aria-label={`Quitar ${p.metodo}`} onClick={() => despachar({ tipo: 'quitar_pago', indice: i })} />
                </span>
              </li>
            ))}
          </ul>
        )}

        {completo && vuelto > 0 && (
          <div className="flex items-center justify-between rounded-2xl bg-emerald-50 p-4 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300" role="status">
            <span className="font-semibold">Vuelto</span>
            <span className="tabular text-3xl font-extrabold">{fmtDinero(aPesos(vuelto))}</span>
          </div>
        )}

        {necesitaCliente && (
          <div>
            <p className="label">Cliente de la cuenta corriente</p>
            <SelectorCliente
              value={cliente}
              onChange={(cl) => {
                setCliente(cl)
                despachar({ tipo: 'cliente', clienteId: cl?.id ?? null })
              }}
            />
          </div>
        )}

        {completo && (
          <p className="text-center text-sm text-stone-500">
            {listo ? (
              <>
                Apretá <kbd className="font-bold">Enter</kbd> para confirmar la venta.
              </>
            ) : (
              'Elegí el cliente para confirmar.'
            )}
          </p>
        )}
      </div>
    </Modal>
  )
}
