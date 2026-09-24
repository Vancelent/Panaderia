import { useId } from 'react'

/** Etiqueta + control + ayuda/error, con ids enlazados para accesibilidad. */
export function Field({ label, hint, error, children, className = '' }) {
  const id = useId()
  const control = typeof children === 'function' ? children(id) : children
  return (
    <div className={className}>
      {label && (
        <label htmlFor={id} className="label">
          {label}
        </label>
      )}
      {control}
      {error ? (
        <p className="mt-1 text-sm text-red-600 dark:text-red-400">{error}</p>
      ) : (
        hint && <p className="mt-1 text-xs text-stone-500">{hint}</p>
      )}
    </div>
  )
}

export function Input({ className = '', ...props }) {
  return <input className={`input ${className}`} {...props} />
}

export function Select({ className = '', children, ...props }) {
  return (
    <select className={`input pr-8 ${className}`} {...props}>
      {children}
    </select>
  )
}

export function Textarea({ className = '', ...props }) {
  return <textarea className={`input min-h-[80px] ${className}`} {...props} />
}
