import { AlertTriangle, Minus, Plus } from 'lucide-react'
import { mensajeError } from '../../lib/api'
import { Button } from './Button'

const TONOS = {
  neutral: 'bg-stone-100 text-stone-700 dark:bg-stone-800 dark:text-stone-300',
  brand: 'bg-brand-100 text-brand-800 dark:bg-brand-900/50 dark:text-brand-200',
  green: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300',
  amber: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
  red: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
  blue: 'bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300',
  violet: 'bg-violet-100 text-violet-800 dark:bg-violet-900/40 dark:text-violet-300',
}

export function Badge({ tone = 'neutral', className = '', children }) {
  return (
    <span
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-semibold ${TONOS[tone]} ${className}`}
    >
      {children}
    </span>
  )
}

export function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-0.5 text-sm text-stone-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  )
}

export function EmptyState({ icon: Icon, title, children, action }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-12 text-center">
      {Icon && (
        <div className="mb-1 rounded-2xl bg-stone-100 p-3 text-stone-400 dark:bg-stone-800">
          <Icon className="h-7 w-7" />
        </div>
      )}
      <p className="font-semibold text-stone-700 dark:text-stone-300">{title}</p>
      {children && <p className="max-w-sm text-sm text-stone-500">{children}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}

export function ErrorState({ error, onRetry }) {
  return (
    <div className="card flex flex-col items-center gap-3 p-8 text-center">
      <AlertTriangle className="h-8 w-8 text-red-500" />
      <p className="font-medium">{mensajeError(error, 'No se pudieron cargar los datos.')}</p>
      {onRetry && (
        <Button variant="secondary" onClick={() => onRetry()}>
          Reintentar
        </Button>
      )}
    </div>
  )
}

export function Stepper({ value, onChange, min = 0, max = 9999, size = 'md' }) {
  const btn = size === 'lg' ? 'h-12 w-12' : 'h-9 w-9'
  return (
    <div className="inline-flex items-center overflow-hidden rounded-xl border border-stone-300 bg-white dark:border-stone-700 dark:bg-stone-950">
      <button
        type="button"
        className={`${btn} grid place-items-center text-stone-600 hover:bg-stone-100 disabled:opacity-40 dark:text-stone-300 dark:hover:bg-stone-800`}
        onClick={() => onChange(Math.max(min, value - 1))}
        disabled={value <= min}
        aria-label="Restar"
      >
        <Minus className="h-4 w-4" />
      </button>
      <input
        type="number"
        inputMode="numeric"
        className={`tabular w-14 border-x border-stone-200 bg-transparent text-center font-bold focus:outline-none dark:border-stone-800 ${size === 'lg' ? 'h-12 text-lg' : 'h-9'}`}
        value={value}
        min={min}
        max={max}
        onChange={(e) => {
          const n = parseInt(e.target.value, 10)
          onChange(Number.isNaN(n) ? min : Math.min(max, Math.max(min, n)))
        }}
        onFocus={(e) => e.target.select()}
        aria-label="Cantidad"
      />
      <button
        type="button"
        className={`${btn} grid place-items-center text-stone-600 hover:bg-stone-100 disabled:opacity-40 dark:text-stone-300 dark:hover:bg-stone-800`}
        onClick={() => onChange(Math.min(max, value + 1))}
        disabled={value >= max}
        aria-label="Sumar"
      >
        <Plus className="h-4 w-4" />
      </button>
    </div>
  )
}

/** Control segmentado (tabs compactas). */
export function Segmented({ options, value, onChange, className = '' }) {
  return (
    <div
      role="tablist"
      className={`inline-flex rounded-xl bg-stone-200/70 p-1 dark:bg-stone-800 ${className}`}
    >
      {options.map((o) => (
        <button
          key={o.value}
          role="tab"
          aria-selected={value === o.value}
          onClick={() => onChange(o.value)}
          className={`rounded-lg px-3 py-1.5 text-sm font-semibold transition ${
            value === o.value
              ? 'bg-white text-stone-900 shadow-sm dark:bg-stone-950 dark:text-white'
              : 'text-stone-600 hover:text-stone-900 dark:text-stone-400 dark:hover:text-white'
          }`}
        >
          {o.label}
          {o.count != null && <span className="ml-1.5 text-xs text-stone-400">{o.count}</span>}
        </button>
      ))}
    </div>
  )
}
