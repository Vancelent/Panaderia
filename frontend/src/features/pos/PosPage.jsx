import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  Banknote,
  History,
  LockKeyhole,
  Search,
  ShoppingBag,
  Trash2,
  X,
} from 'lucide-react'
import { useAuth } from '../../auth/context'
import { Button } from '../../components/ui/Button'
import { Field, Input } from '../../components/ui/Field'
import { Badge, EmptyState, ErrorState, Stepper } from '../../components/ui/misc'
import { PantallaCarga } from '../../components/ui/Spinner'
import { useToast } from '../../components/ui/toast'
import { mensajeError, post } from '../../lib/api'
import { fmtDinero, fmtHora } from '../../lib/format'
import { qk, useProductos, useTurnoActual } from '../../lib/queries'
import { nivelStock } from '../../lib/stock'
import { MermaModal } from '../stock/MermaModal'
import { CierreModal, CobroModal, VentasTurnoModal } from './modales'

const MULTIPLICADORES = [
  { n: 1, label: '×1' },
  { n: 2, label: '×2' },
  { n: 6, label: '½ doc' },
  { n: 12, label: 'Doc' },
]

export default function PosPage() {
  const turno = useTurnoActual()
  if (turno.isLoading) return <PantallaCarga texto="Verificando turno…" />
  if (turno.isError) return <ErrorState error={turno.error} onRetry={turno.refetch} />
  return turno.data ? <Terminal turno={turno.data} /> : <AbrirTurno />
}

function AbrirTurno() {
  const qc = useQueryClient()
  const toast = useToast()
  const { user } = useAuth()
  const [monto, setMonto] = useState('')
  const abrir = useMutation({
    mutationFn: () => post('/turnos', { efectivo_inicial: Number(monto) }),
    onSuccess: (t) => {
      qc.setQueryData(qk.turnoActual, t)
      toast.ok('Turno abierto. ¡Buenas ventas!')
    },
    onError: (e) => toast.error(mensajeError(e)),
  })
  const valido = monto !== '' && Number(monto) >= 0

  return (
    <div className="flex min-h-[70vh] items-center justify-center">
      <form
        className="card w-full max-w-sm p-6"
        onSubmit={(e) => {
          e.preventDefault()
          if (valido) abrir.mutate()
        }}
      >
        <div className="mb-5 flex items-center gap-3">
          <div className="grid h-12 w-12 place-items-center rounded-2xl bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
            <Banknote className="h-6 w-6" />
          </div>
          <div>
            <h1 className="text-xl font-bold">Abrir caja</h1>
            <p className="text-sm text-stone-500">Hola {user.nombre || user.username}, contá el fondo inicial.</p>
          </div>
        </div>
        <Field label="Efectivo en el cajón" hint="Billetes y monedas con los que arrancás el turno.">
          {(id) => (
            <Input
              id={id}
              type="number"
              inputMode="decimal"
              step="0.01"
              min="0"
              autoFocus
              className="tabular h-14 text-center text-2xl font-bold"
              placeholder="$ 0,00"
              value={monto}
              onChange={(e) => setMonto(e.target.value)}
            />
          )}
        </Field>
        <Button type="submit" variant="success" size="lg" className="mt-5 w-full" loading={abrir.isPending} disabled={!valido}>
          Iniciar turno
        </Button>
      </form>
    </div>
  )
}

function Terminal({ turno }) {
  const productosQ = useProductos()
  const toast = useToast()
  const [carrito, setCarrito] = useState({}) // { producto_id: cantidad }
  const [busqueda, setBusqueda] = useState('')
  const [categoria, setCategoria] = useState(null)
  const [mult, setMult] = useState(1)
  const [modal, setModal] = useState(null) // 'cobro' | 'cierre' | 'merma' | 'ventas'
  const [ticketMovil, setTicketMovil] = useState(false)
  const buscador = useRef(null)

  const productos = useMemo(() => productosQ.data ?? [], [productosQ.data])
  const porId = useMemo(() => Object.fromEntries(productos.map((p) => [p.id, p])), [productos])
  const categorias = useMemo(
    () => [...new Set(productos.map((p) => p.categoria).filter(Boolean))].sort(),
    [productos],
  )
  const visibles = useMemo(() => {
    const q = busqueda.trim().toLowerCase()
    return productos.filter(
      (p) => (!categoria || p.categoria === categoria) && (!q || p.nombre.toLowerCase().includes(q)),
    )
  }, [productos, busqueda, categoria])

  const items = Object.entries(carrito)
    .map(([id, cant]) => ({ producto: porId[id], cantidad: cant }))
    .filter((i) => i.producto)
  const total = items.reduce((t, i) => t + i.cantidad * i.producto.precio_venta, 0)
  const unidades = items.reduce((t, i) => t + i.cantidad, 0)

  const agregar = (p, n = mult) => {
    const actual = carrito[p.id] ?? 0
    const nueva = Math.min(actual + n, p.stock_mostrador)
    if (nueva === actual) {
      toast.info(`No hay más ${p.nombre} en el mostrador.`)
      return
    }
    if (nueva < actual + n) toast.info(`Solo quedan ${p.stock_mostrador} de ${p.nombre}.`)
    setCarrito((c) => ({ ...c, [p.id]: nueva }))
    setMult(1)
  }
  const fijar = (id, n) =>
    setCarrito((c) => {
      const { [id]: _, ...resto } = c
      return n > 0 ? { ...resto, [id]: n } : resto
    })

  // Atajos: "/" busca, F9 cobra, Esc limpia la búsqueda
  useEffect(() => {
    const onKey = (e) => {
      if (modal) return
      const enCampo = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)
      if (e.key === '/' && !enCampo) {
        e.preventDefault()
        buscador.current?.focus()
      } else if (e.key === 'F9' && items.length) {
        e.preventDefault()
        setModal('cobro')
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [modal, items.length])

  if (productosQ.isError) return <ErrorState error={productosQ.error} onRetry={productosQ.refetch} />

  const ticket = (
    <Ticket
      items={items}
      total={total}
      onFijar={fijar}
      onVaciar={() => setCarrito({})}
      onCobrar={() => setModal('cobro')}
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
                value={busqueda}
                onChange={(e) => setBusqueda(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && visibles[0]) {
                    agregar(visibles[0])
                    setBusqueda('')
                  } else if (e.key === 'Escape') setBusqueda('')
                }}
              />
            </div>
            <div className="flex h-12 shrink-0 gap-1 rounded-xl bg-stone-200/70 p-1 dark:bg-stone-800" role="group" aria-label="Cantidad por toque">
              {MULTIPLICADORES.map(({ n, label }) => (
                <button
                  key={n}
                  onClick={() => setMult(n)}
                  aria-pressed={mult === n}
                  className={`rounded-lg px-2 text-sm font-bold sm:px-2.5 ${
                    mult === n ? 'bg-brand-600 text-white shadow' : 'text-stone-600 dark:text-stone-300'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <Badge tone="green" className="hidden h-8 px-3 sm:inline-flex">
              <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-500" />
              Turno #{turno.id} · {fmtHora(turno.fecha_apertura)}
            </Badge>
            <Button variant="secondary" size="icon" icon={History} onClick={() => setModal('ventas')} title="Últimas ventas" aria-label="Últimas ventas" />
            <Button variant="secondary" size="icon" icon={AlertTriangle} onClick={() => setModal('merma')} title="Registrar merma" aria-label="Registrar merma" />
            <Button variant="secondary" icon={LockKeyhole} onClick={() => setModal('cierre')}>
              <span className="hidden sm:inline">Cerrar caja</span>
            </Button>
          </div>
          <div className="scrollbar-none -mx-1 flex gap-2 overflow-x-auto px-1 pb-0.5">
            <Chip activo={!categoria} onClick={() => setCategoria(null)}>Todo</Chip>
            {categorias.map((c) => (
              <Chip key={c} activo={categoria === c} onClick={() => setCategoria(c)}>
                {c}
              </Chip>
            ))}
          </div>
        </div>

        <div className="scrollbar-thin flex-1 overflow-y-auto overflow-x-hidden p-3 sm:p-4">
          {productosQ.isLoading ? (
            <PantallaCarga />
          ) : visibles.length === 0 ? (
            <EmptyState icon={Search} title="Sin resultados">
              Probá con otro nombre o categoría.
            </EmptyState>
          ) : (
            <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-3">
              {visibles.map((p) => (
                <TarjetaProducto key={p.id} p={p} enCarrito={carrito[p.id] ?? 0} onClick={() => agregar(p)} />
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
          <button onClick={() => setTicketMovil(true)} className="flex flex-1 items-center gap-3 text-left" disabled={!items.length}>
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
              <p className="tabular text-xl font-extrabold">{fmtDinero(total)}</p>
            </div>
          </button>
          <Button size="lg" variant="success" disabled={!items.length} onClick={() => setModal('cobro')}>
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

      <CobroModal
        open={modal === 'cobro'}
        onClose={() => setModal(null)}
        items={items}
        total={total}
        onVendido={() => {
          setCarrito({})
          setTicketMovil(false)
          setModal(null)
        }}
      />
      <CierreModal open={modal === 'cierre'} onClose={() => setModal(null)} carritoConItems={items.length > 0} />
      <MermaModal open={modal === 'merma'} onClose={() => setModal(null)} productos={productos} />
      <VentasTurnoModal open={modal === 'ventas'} onClose={() => setModal(null)} />
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
  const agotado = p.stock_mostrador <= 0
  const lleno = enCarrito >= p.stock_mostrador
  const nivel = nivelStock(p.stock_mostrador - enCarrito, p.stock_minimo)
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
          {agotado ? 'Agotado' : `${p.stock_mostrador - enCarrito} u`}
        </Badge>
      </div>
    </button>
  )
}

function Ticket({ items, total, onFijar, onVaciar, onCobrar }) {
  return (
    <div className="flex min-h-0 w-full flex-col">
      <div className="flex items-center justify-between px-4 pb-2 pt-4">
        <h2 className="font-bold">Ticket</h2>
        {items.length > 0 && (
          <Button variant="ghost" size="sm" icon={Trash2} onClick={onVaciar}>
            Vaciar
          </Button>
        )}
      </div>
      <div className="scrollbar-thin min-h-[120px] flex-1 overflow-y-auto px-2">
        {items.length === 0 ? (
          <EmptyState icon={ShoppingBag} title="Ticket vacío">
            Tocá un producto para agregarlo.
          </EmptyState>
        ) : (
          <ul className="divide-y divide-stone-100 dark:divide-stone-800">
            {items.map(({ producto: p, cantidad }) => (
              <li key={p.id} className="px-2 py-2.5">
                <div className="flex items-baseline justify-between gap-3">
                  <p className="min-w-0 font-semibold leading-snug">{p.nombre}</p>
                  <p className="tabular shrink-0 font-bold">{fmtDinero(cantidad * p.precio_venta)}</p>
                </div>
                <div className="mt-1.5 flex items-center justify-between gap-3">
                  <p className="tabular text-xs text-stone-500">{fmtDinero(p.precio_venta)} c/u</p>
                  <Stepper value={cantidad} onChange={(n) => onFijar(p.id, n)} max={p.stock_mostrador} />
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="space-y-3 border-t border-stone-200 p-4 dark:border-stone-800">
        <div className="flex items-baseline justify-between">
          <span className="text-sm font-semibold uppercase tracking-wide text-stone-500">Total</span>
          <span className="tabular text-3xl font-extrabold tracking-tight">{fmtDinero(total)}</span>
        </div>
        <Button variant="success" size="xl" className="w-full" disabled={!items.length} onClick={onCobrar}>
          Cobrar <kbd className="ml-1 rounded bg-white/20 px-1.5 py-0.5 text-xs font-medium">F9</kbd>
        </Button>
      </div>
    </div>
  )
}
