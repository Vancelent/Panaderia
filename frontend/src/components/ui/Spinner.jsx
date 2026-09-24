import { Loader2 } from 'lucide-react'

export function Spinner({ className = 'h-5 w-5' }) {
  return <Loader2 className={`animate-spin text-brand-600 ${className}`} aria-label="Cargando" />
}

export function PantallaCarga({ texto = 'Cargando…' }) {
  return (
    <div className="flex min-h-[50vh] flex-col items-center justify-center gap-3 text-stone-500">
      <Spinner className="h-8 w-8" />
      <p className="text-sm font-medium">{texto}</p>
    </div>
  )
}
