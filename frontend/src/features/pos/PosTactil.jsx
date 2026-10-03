import { useEffect, useRef, useState } from 'react'
import { Search, ShoppingBag, Trash2, X } from 'lucide-react'
import { caja } from '@panaderia/core'
import { Button } from '../../components/ui/Button'
import { Badge, EmptyState, ErrorState, Stepper } from '../../components/ui/misc'
import { PantallaCarga } from '../../components/ui/Spinner'
import { fmtDinero } from '../../lib/format'
import { nivelStock } from '../../lib/stock'
import BarraCaja from './BarraCaja'

const aPesos = (c) => c / 100

/**
 * Caja táctil: grilla de productos grandes, multiplicadores de ½ docena y docena y ticket con selector de
 * cantidad. Es la misma lógica que la vista de teclado (`usePos`), con otra cara para tablets y celulares.
 */
export default function PosTactil({ pos, barra, abrirCobro, modalAbierto }) {
  const { estado, despachar, productosQ, resultados, categorias, lineas, totalCentavos, unidades } = pos
  const [ticketMovil, setTicketMovil] = useState(false)
  const buscador = useRef(null)

  // Atajos: "/" busca, F9 cobra
  useEffect(() => {
    if (modalAbierto) return undefined
    const onKey = (e) => {
      const enCampo = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)
      if (e.key === '/' && !enCampo) {
        e.preventDefault()
        buscador.current?.focus()
      } else if (e.key === 'F9' && lineas.length) {
        e.preventDefault()
        abrirCobro()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [modalAbierto, lineas.length, abrirCobro])

  if (productosQ.isError) return <ErrorState error={productosQ.error} onRetry={productosQ.refetch} />

  const ticket = (
    <Ticket
      lineas={lineas}
      totalCentavos={totalCentavos}
      onFijar={(productoId, cantidad) => despachar({ tipo: 'fijar_cantidad', productoId, cantidad })}
      onVaciar={() => despachar({ tipo: 'vaciar' })}
      onCobrar={abrirCobro}
    />
  )

  return (
    <div className="-m-4 flex h-[calc(100dvh-3.5rem)] flex-col sm:-m-6 lg:h-dvh lg:flex-row">
      {/* Catálogo */}
      <section className="flex min-h-0 min-w-0 flex-1 flex-col">
        <div className="space-y-3 border-b border-stone-200 bg-white/70 p-3 backdrop-blur dark:border-stone-800 dark:bg-stone-900/70 sm:p-4">
          <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
            <div className="relative w-full min-w-[200px] sm:w-auto sm:flex-1">
              <Search className="pointer-events-none absolute left-3.5 top-1/2 h-5 w-5 -translate-y-1/2 text-stone-400" />
              <input
                ref={buscador}
                className="input h-12 pl-11 text-base"
                placeholder="Buscar producto  ( / )"
                value={estado.consulta}
                onChange={(e) => despachar({ tipo: 'escribir', texto: e.target.value })}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') despachar({ tipo: 'enter' })
                  else if (e.key === 'Escape') despachar({ tipo: 'limpiar_busqueda', conservarCategoria: true })
                }}
              />
            </div>
            <div className="flex h-12 shrink-0 gap-1 rounded-xl bg-stone-200/70 p-1 dark:bg-stone-800" role="group" aria-label="Cantidad por toque">
              {caja.MULTIPLICADORES.map(({ n, label }) => (
                <button
                  key={n}
                  onClick={() => despachar({ tipo: 'fijar_multiplicador', n })}
                  aria-pressed={estado.multiplicador === n}
                  className={`rounded-lg px-2 text-sm font-bold sm:px-2.5 ${
                    estado.multiplicador === n ? 'bg-brand-600 text-white shadow' : 'text-stone-600 dark:text-stone-300'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <BarraCaja {...barra} />
          </div>
          <div className="scrollbar-none -mx-1 flex gap-2 overflow-x-auto px-1 pb-0.5">
            <Chip activo={!estado.categoria} onClick={() => despachar({ tipo: 'categoria', categoria: null })}>
              Todo
            </Chip>
            {categorias.map((c) => (
              <Chip key={c} activo={estado.categoria === c} onClick={() => despachar({ tipo: 'categoria', categoria: c })}>
                {c}
              </Chip>
            ))}
          </div>
        </div>

        <div className="scrollbar-thin flex-1 overflow-y-auto overflow-x-hidden p-3 sm:p-4">
          {productosQ.isLoading ? (
            <PantallaCarga />
          ) : resultados.length === 0 ? (
            <EmptyState icon={Search} title="Sin resultados">
              Probá con otro nombre o categoría.
            </EmptyState>
          ) : (
            <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-3">
              {resultados.map((p) => (
                <TarjetaProducto
                  key={p.id}
                  p={p}
                  enCarrito={caja.cantidadEnTicket(estado, p.id)}
                  onClick={() => despachar({ tipo: 'agregar', productoId: p.id })}
                />
              ))}
            </div>
          )}
        </div>
      </section>

      {/* Ticket lateral (escritorio / tablet horizontal) */}
      <aside className="hidden w-[380px] shrink-0 border-l border-stone-200 bg-white dark:border-stone-800 dark:bg-stone-900 lg:flex">
        {ticket}
      </aside>

      {/* Barra inferior + ticket desplegable (móvil) */}
      <div className="border-t border-stone-200 bg-white p-3 dark:border-stone-800 dark:bg-stone-900 lg:hidden">
        <div className="flex items-center gap-3">
          <button onClick={() => setTicketMovil(true)} className="flex flex-1 items-center gap-3 text-left" disabled={!lineas.length}>
            <div className="relative grid h-11 w-11 place-items-center rounded-xl bg-stone-100 dark:bg-stone-800">
              <ShoppingBag className="h-5 w-5" />
              {unidades > 0 && (
                <span className="absolute -right-1 -top-1 grid h-5 min-w-5 place-items-center rounded-full bg-brand-600 px-1 text-[11px] font-bold text-white">
                  {unidades}
                </span>
              )}
            </div>
            <div>
              <p className="text-xs text-stone-500">Total</p>
              <p className="tabular text-xl font-extrabold">{fmtDinero(aPesos(totalCentavos))}</p>
            </div>
          </button>
          <Button size="lg" variant="success" disabled={!lineas.length} onClick={abrirCobro}>
            Cobrar
          </Button>
        </div>
      </div>
      {ticketMovil && (
        <div className="fixed inset-0 z-40 flex flex-col justify-end lg:hidden">
          <div className="absolute inset-0 bg-stone-950/50" onClick={() => setTicketMovil(false)} />
          <div className="relative flex max-h-[80vh] animate-slide-up flex-col rounded-t-3xl bg-white dark:bg-stone-900">
            <button onClick={() => setTicketMovil(false)} className="absolute right-3 top-3 rounded-lg p-2" aria-label="Cerrar ticket">
              <X className="h-5 w-5" />
            </button>
            {ticket}
          </div>
        </div>
      )}
    </div>
  )
}

function Chip({ activo, children, ...props }) {
  return (
    <button
      className={`shrink-0 rounded-full px-3.5 py-1.5 text-sm font-semibold transition ${
        activo
          ? 'bg-stone-900 text-white dark:bg-white dark:text-stone-900'
          : 'bg-white text-stone-700 ring-1 ring-stone-200 hover:bg-stone-50 dark:bg-stone-900 dark:text-stone-300 dark:ring-stone-700'
      }`}
      {...props}
    >
      {children}
    </button>
  )
}

function TarjetaProducto({ p, enCarrito, onClick }) {
  const agotado = p.stock_disponible <= 0
  const lleno = enCarrito >= p.stock_disponible
  const disponible = Math.max(0, p.stock_disponible - enCarrito)
  const nivel = nivelStock(disponible, p.stock_minimo)
  return (
    <button
      onClick={onClick}
      disabled={agotado}
      className={`group relative flex min-h-[112px] min-w-0 flex-col justify-between rounded-2xl border p-3.5 text-left transition active:scale-[0.97] ${
        enCarrito
          ? 'border-brand-400 bg-brand-50 ring-1 ring-brand-400 dark:border-brand-600 dark:bg-brand-950/40'
          : 'border-stone-200 bg-white hover:border-stone-300 hover:shadow-md dark:border-stone-800 dark:bg-stone-900 dark:hover:border-stone-700'
      } ${agotado ? 'cursor-not-allowed opacity-50 grayscale' : ''} ${lleno && !agotado ? 'opacity-70' : ''}`}
    >
      {enCarrito > 0 && (
        <span className="absolute -right-2 -top-2 grid h-7 min-w-7 place-items-center rounded-full bg-brand-600 px-1.5 text-sm font-bold text-white shadow">
          {enCarrito}
        </span>
      )}
      <p className="line-clamp-2 font-semibold leading-snug">{p.nombre}</p>
      <div className="mt-2 flex flex-wrap items-end justify-between gap-x-2 gap-y-1">
        <p className="tabular text-lg font-extrabold text-brand-700 dark:text-brand-300">{fmtDinero(p.precio_venta)}</p>
        <Badge tone={agotado ? 'red' : nivel.tone === 'green' ? 'neutral' : nivel.tone}>
          {agotado ? 'Agotado' : `${disponible} u`}
        </Badge>
      </div>
    </button>
  )
}

function Ticket({ lineas, totalCentavos, onFijar, onVaciar, onCobrar }) {
  return (
    <div className="flex min-h-0 w-full flex-col">
      <div className="flex items-center justify-between px-4 pb-2 pt-4">
        <h2 className="font-bold">Ticket</h2>
        {lineas.length > 0 && (
          <Button variant="ghost" size="sm" icon={Trash2} onClick={onVaciar}>
            Vaciar
          </Button>
        )}
      </div>
      <div className="scrollbar-thin min-h-[120px] flex-1 overflow-y-auto px-2">
        {lineas.length === 0 ? (
          <EmptyState icon={ShoppingBag} title="Ticket vacío">
            Tocá un producto para agregarlo.
          </EmptyState>
        ) : (
          <ul className="divide-y divide-stone-100 dark:divide-stone-800">
            {lineas.map(({ producto: p, cantidad, subtotalCentavos }) => (
              <li key={p.id} className="px-2 py-2.5">
                <div className="flex items-baseline justify-between gap-3">
                  <p className="min-w-0 font-semibold leading-snug">{p.nombre}</p>
                  <p className="tabular shrink-0 font-bold">{fmtDinero(aPesos(subtotalCentavos))}</p>
                </div>
                <div className="mt-1.5 flex items-center justify-between gap-3">
                  <p className="tabular text-xs text-stone-500">{fmtDinero(p.precio_venta)} c/u</p>
                  <Stepper value={cantidad} onChange={(n) => onFijar(p.id, n)} max={p.stock_disponible} />
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="space-y-3 border-t border-stone-200 p-4 dark:border-stone-800">
        <div className="flex items-baseline justify-between">
          <span className="text-sm font-semibold uppercase tracking-wide text-stone-500">Total</span>
          <span className="tabular text-3xl font-extrabold tracking-tight">{fmtDinero(aPesos(totalCentavos))}</span>
        </div>
        <Button variant="success" size="xl" className="w-full" disabled={!lineas.length} onClick={onCobrar}>
          Cobrar <kbd className="ml-1 rounded bg-white/20 px-1.5 py-0.5 text-xs font-medium">F9</kbd>
        </Button>
      </div>
    </div>
  )
}
