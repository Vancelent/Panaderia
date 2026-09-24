import { useCallback, useMemo, useRef, useState } from 'react'
import { AlertCircle, CheckCircle2, Info, X } from 'lucide-react'
import { ToastContext } from './toast'

const ESTILOS = {
  ok: { icon: CheckCircle2, cls: 'border-emerald-200 dark:border-emerald-900', ico: 'text-emerald-600' },
  error: { icon: AlertCircle, cls: 'border-red-200 dark:border-red-900', ico: 'text-red-600' },
  info: { icon: Info, cls: 'border-sky-200 dark:border-sky-900', ico: 'text-sky-600' },
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const seq = useRef(0)

  const cerrar = useCallback((id) => setToasts((t) => t.filter((x) => x.id !== id)), [])

  const mostrar = useCallback(
    (tipo, mensaje, ms) => {
      const id = ++seq.current
      setToasts((t) => [...t.slice(-3), { id, tipo, mensaje }])
      setTimeout(() => cerrar(id), ms ?? (tipo === 'error' ? 6000 : 3500))
    },
    [cerrar],
  )

  const api = useMemo(
    () => ({
      ok: (m, ms) => mostrar('ok', m, ms),
      error: (m, ms) => mostrar('error', m, ms),
      info: (m, ms) => mostrar('info', m, ms),
    }),
    [mostrar],
  )

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        className="pointer-events-none fixed inset-x-0 top-3 z-[60] flex flex-col items-center gap-2 px-3 sm:left-auto sm:right-4 sm:top-4 sm:items-end"
        aria-live="polite"
      >
        {toasts.map(({ id, tipo, mensaje }) => {
          const { icon: Icon, cls, ico } = ESTILOS[tipo]
          return (
            <div
              key={id}
              role={tipo === 'error' ? 'alert' : 'status'}
              className={`pointer-events-auto flex w-full max-w-sm animate-slide-up items-start gap-3 rounded-2xl border bg-white p-3.5 shadow-lg dark:bg-stone-900 ${cls}`}
            >
              <Icon className={`mt-0.5 h-5 w-5 shrink-0 ${ico}`} />
              <p className="flex-1 text-sm font-medium">{mensaje}</p>
              <button onClick={() => cerrar(id)} className="text-stone-400 hover:text-stone-700" aria-label="Cerrar aviso">
                <X className="h-4 w-4" />
              </button>
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}
