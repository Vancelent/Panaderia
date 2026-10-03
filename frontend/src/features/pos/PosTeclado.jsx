import { useEffect, useRef } from 'react'
import { Search, ShoppingBag, Trash2 } from 'lucide-react'
import { caja } from '@panaderia/core'
import { Button } from '../../components/ui/Button'
import { Badge, EmptyState, ErrorState } from '../../components/ui/misc'
import { PantallaCarga } from '../../components/ui/Spinner'
import { fmtDinero } from '../../lib/format'
import { nivelStock } from '../../lib/stock'
import BarraCaja from './BarraCaja'

const aPesos = (c) => c / 100

const ATAJOS = [
  ['F2', 'buscador'],
  ['Enter', 'agregar'],
  ['↑ ↓', 'elegir'],
  ['12*', 'cantidad'],
  ['F9', 'cobrar'],
  ['F10', 'cerrar caja'],
  ['Esc', 'limpiar'],
]

/**
 * Caja orientada a teclado (docs/rfc-001 §6): el foco vive en el buscador y una venta típica de 3
 * productos se resuelve sin tocar el mouse. Es una vista del controlador compartido (`usePos`).
 *
 * Flujo: escribir filtra al tipear · Enter agrega el resaltado (o el código exacto) · "12*med" Enter agrega 12 ·
 * ↑/↓ elige · Tab recorre buscador → resultados → ticket → cobrar · en el ticket + − Supr · F9 cobra.
 */
export default function PosTeclado({ pos, barra, abrirCobro, modalAbierto }) {
  const { estado, despachar, productosQ, resultados, lineas, anuncio, totalCentavos, unidades } = pos
  const buscador = useRef(null)

  // Después de agregar un ítem, o de cerrar un modal (cobro, merma…), el foco vuelve siempre al buscador.
  // Quitar o cambiar la cantidad de una línea del ticket NO lo mueve: se sigue operando sobre el ticket.
  const tipoAviso = estado.aviso?.tipo
  const agregando = ['agregado', 'tope', 'sin_stock', 'sin_resultados'].includes(tipoAviso)
  useEffect(() => {
    if (!modalAbierto) buscador.current?.focus()
  }, [modalAbierto])
  useEffect(() => {
    if (!modalAbierto && agregando) buscador.current?.focus()
  }, [modalAbierto, agregando, estado.aviso])

  // F2 vuelve al buscador desde cualquier lugar; F9 cobra; F10 cierra la caja
  useEffect(() => {
    if (modalAbierto) return undefined
    const onKey = (e) => {
      if (e.key === 'F2') {
        e.preventDefault()
        buscador.current?.focus()
      } else if (e.key === 'F9' && lineas.length) {
        e.preventDefault()
        abrirCobro()
      } else if (e.key === 'F10') {
        e.preventDefault()
        barra.onCierre()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [modalAbierto, lineas.length, abrirCobro, barra])

  // Mantiene visible la fila resaltada de los resultados
  useEffect(() => {
    document.getElementById(`resultado-${estado.seleccion}`)?.scrollIntoView({ block: 'nearest' })
  }, [estado.seleccion, resultados])

  if (productosQ.isError) return <ErrorState error={productosQ.error} onRetry={productosQ.refetch} />

  const multiplicador = caja.multiplicadorActivo(estado)

  const alBuscar = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      despachar({ tipo: 'enter' })
    } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      despachar({ tipo: 'mover', delta: e.key === 'ArrowDown' ? 1 : -1 })
    } else if (e.key === 'Escape') {
      despachar({ tipo: 'limpiar_busqueda' })
    }
  }

  const alResultado = (e) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      despachar({ tipo: 'mover', delta: e.key === 'ArrowDown' ? 1 : -1 })
    } else if (e.key === 'Enter') {
      e.preventDefault()
      despachar({ tipo: 'enter' })
    }
  }

  const alTicket = (e) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      despachar({ tipo: 'ticket_mover', delta: e.key === 'ArrowDown' ? 1 : -1 })
    } else if (e.key === '+' || e.key === '=') {
      e.preventDefault()
      despachar({ tipo: 'ticket_sumar' })
    } else if (e.key === '-') {
      e.preventDefault()
      despachar({ tipo: 'ticket_restar' })
    } else if (e.key === 'Delete' || e.key === 'Backspace') {
      e.preventDefault()
      despachar({ tipo: 'ticket_quitar' })
    }
  }

  return (
    <div className="-m-4 flex h-[calc(100dvh-3.5rem)] flex-col sm:-m-6 lg:h-dvh">
      {/* Se anuncia cada alta al ticket y el total a los lectores de pantalla */}
      <div className="sr-only" aria-live="polite" role="status">
        {anuncio} {lineas.length > 0 && `Total ${fmtDinero(aPesos(totalCentavos))}`}
      </div>

      <div className="flex flex-wrap items-center gap-2 border-b border-stone-200 bg-white/70 p-3 backdrop-blur dark:border-stone-800 dark:bg-stone-900/70 sm:p-4">
        <div className="relative min-w-[240px] flex-1">
          <Search className="pointer-events-none absolute left-3.5 top-1/2 h-5 w-5 -translate-y-1/2 text-stone-400" />
          <input
            ref={buscador}
            autoFocus
            className="input h-14 pl-11 pr-24 text-lg"
            placeholder="Escribí el producto, el código o  12*med"
            aria-label="Buscar producto"
            aria-controls="resultados-pos"
            aria-activedescendant={resultados.length ? `resultado-${estado.seleccion}` : undefined}
            autoComplete="off"
            spellCheck={false}
            value={estado.consulta}
            onChange={(e) => despachar({ tipo: 'escribir', texto: e.target.value })}
            onKeyDown={alBuscar}
          />
          {multiplicador > 1 && (
            <span className="absolute right-3 top-1/2 -translate-y-1/2 rounded-lg bg-brand-600 px-2.5 py-1 text-sm font-bold text-white">
              ×{multiplicador}
            </span>
          )}
        </div>
        <BarraCaja {...barra} />
      </div>

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        {/* Resultados */}
        <section className="flex min-h-0 min-w-0 flex-1 flex-col">
          <div className="scrollbar-thin flex-1 overflow-y-auto p-3 sm:p-4">
            {productosQ.isLoading ? (
              <PantallaCarga />
            ) : resultados.length === 0 ? (
              <EmptyState icon={Search} title="Sin resultados">
                Probá con otro nombre o con el código del producto.
              </EmptyState>
            ) : (
              <ul
                id="resultados-pos"
                role="listbox"
                tabIndex={0}
                aria-label="Resultados de la búsqueda"
                onKeyDown={alResultado}
                className="divide-y divide-stone-100 overflow-hidden rounded-2xl border border-stone-200 bg-white outline-none focus-visible:ring-2 focus-visible:ring-brand-400 dark:divide-stone-800 dark:border-stone-800 dark:bg-stone-900"
              >
                {resultados.map((p, i) => {
                  const disponible = caja.disponibleParaAgregar(estado, p)
                  const nivel = nivelStock(disponible, p.stock_minimo)
                  const activo = i === estado.seleccion
                  return (
                    <li
                      key={p.id}
                      id={`resultado-${i}`}
                      role="option"
                      aria-selected={activo}
                      onMouseDown={(e) => e.preventDefault() /* no pierde el foco del buscador */}
                      onClick={() => despachar({ tipo: 'agregar', productoId: p.id })}
                      className={`flex cursor-pointer items-center gap-3 px-4 py-3 ${
                        activo ? 'bg-brand-50 ring-2 ring-inset ring-brand-400 dark:bg-brand-950/40' : 'hover:bg-stone-50 dark:hover:bg-stone-800/50'
                      } ${disponible <= 0 ? 'opacity-50' : ''}`}
                    >
                      <span className="tabular w-14 shrink-0 text-sm font-semibold text-stone-400">{p.codigo ?? ''}</span>
                      <span className="min-w-0 flex-1 truncate text-lg font-semibold">{p.nombre}</span>
                      <span className="tabular shrink-0 text-lg font-extrabold text-brand-700 dark:text-brand-300">
                        {fmtDinero(p.precio_venta)}
                      </span>
                      <Badge tone={disponible <= 0 ? 'red' : nivel.tone === 'green' ? 'neutral' : nivel.tone} className="w-16 justify-center">
                        {disponible <= 0 ? 'Agotado' : `${disponible} u`}
                      </Badge>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
        </section>

        {/* Ticket */}
        <aside className="flex min-h-0 w-full shrink-0 flex-col border-t border-stone-200 bg-white dark:border-stone-800 dark:bg-stone-900 lg:w-[400px] lg:border-l lg:border-t-0">
          <div className="flex items-center justify-between px-4 pb-2 pt-4">
            <h2 className="font-bold">Ticket</h2>
            {lineas.length > 0 && (
              <Button variant="ghost" size="sm" icon={Trash2} onClick={() => despachar({ tipo: 'vaciar' })}>
                Vaciar
              </Button>
            )}
          </div>
          <div className="scrollbar-thin min-h-[120px] flex-1 overflow-y-auto px-2">
            {lineas.length === 0 ? (
              <EmptyState icon={ShoppingBag} title="Ticket vacío">
                Escribí un producto y apretá Enter.
              </EmptyState>
            ) : (
              <ul
                role="listbox"
                tabIndex={0}
                aria-label="Ticket"
                aria-activedescendant={`linea-${estado.lineaSel}`}
                onKeyDown={alTicket}
                className="divide-y divide-stone-100 rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-brand-400 dark:divide-stone-800"
              >
                {lineas.map(({ producto: p, cantidad, subtotalCentavos, excede }, i) => (
                  <li
                    key={p.id}
                    id={`linea-${i}`}
                    role="option"
                    aria-selected={i === estado.lineaSel}
                    className={`px-3 py-2.5 ${i === estado.lineaSel ? 'bg-brand-50 dark:bg-brand-950/40' : ''}`}
                  >
                    <div className="flex items-baseline justify-between gap-3">
                      <p className="min-w-0 font-semibold leading-snug">
                        <span className="tabular mr-2 text-brand-700 dark:text-brand-300">{cantidad}×</span>
                        {p.nombre}
                      </p>
                      <p className="tabular shrink-0 font-bold">{fmtDinero(aPesos(subtotalCentavos))}</p>
                    </div>
                    <p className="tabular text-xs text-stone-500">
                      {fmtDinero(p.precio_venta)} c/u
                      {excede && <span className="ml-2 font-semibold text-red-600">· ya no hay tanto stock</span>}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </div>
          {lineas.length > 0 && (
            <p className="px-4 pb-1 text-xs text-stone-500">
              En el ticket: <kbd className="font-bold">↑↓</kbd> elegir · <kbd className="font-bold">+</kbd>
              <kbd className="font-bold">−</kbd> cantidad · <kbd className="font-bold">Supr</kbd> quitar
            </p>
          )}
          <div className="space-y-3 border-t border-stone-200 p-4 dark:border-stone-800">
            <div className="flex items-baseline justify-between">
              <span className="text-sm font-semibold uppercase tracking-wide text-stone-500">Total · {unidades} u</span>
              <span className="tabular text-3xl font-extrabold tracking-tight">{fmtDinero(aPesos(totalCentavos))}</span>
            </div>
            <Button variant="success" size="xl" className="w-full" disabled={!lineas.length} onClick={abrirCobro}>
              Cobrar <kbd className="ml-1 rounded bg-white/20 px-1.5 py-0.5 text-xs font-medium">F9</kbd>
            </Button>
          </div>
        </aside>
      </div>

      <div className="hidden flex-wrap gap-x-4 gap-y-1 border-t border-stone-200 bg-stone-50 px-4 py-1.5 text-xs text-stone-500 dark:border-stone-800 dark:bg-stone-950/40 sm:flex">
        {ATAJOS.map(([tecla, texto]) => (
          <span key={tecla}>
            <kbd className="rounded bg-stone-200 px-1.5 py-0.5 font-bold text-stone-700 dark:bg-stone-800 dark:text-stone-300">{tecla}</kbd> {texto}
          </span>
        ))}
      </div>
    </div>
  )
}
