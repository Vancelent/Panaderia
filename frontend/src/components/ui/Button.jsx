import { Loader2 } from 'lucide-react'

const VARIANTES = {
  primary:
    'bg-brand-600 text-white shadow-sm hover:bg-brand-700 active:bg-brand-800 dark:bg-brand-600 dark:hover:bg-brand-500',
  secondary:
    'border border-stone-300 bg-white text-stone-800 shadow-sm hover:bg-stone-50 active:bg-stone-100 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-100 dark:hover:bg-stone-800',
  ghost:
    'text-stone-700 hover:bg-stone-200/70 active:bg-stone-200 dark:text-stone-300 dark:hover:bg-stone-800',
  danger: 'bg-red-600 text-white shadow-sm hover:bg-red-700 active:bg-red-800',
  success: 'bg-emerald-600 text-white shadow-sm hover:bg-emerald-700 active:bg-emerald-800',
  soft: 'bg-brand-50 text-brand-800 hover:bg-brand-100 dark:bg-brand-950/60 dark:text-brand-200 dark:hover:bg-brand-900/60',
}

const TAMANOS = {
  sm: 'h-8 gap-1.5 rounded-lg px-3 text-sm',
  md: 'h-10 gap-2 rounded-xl px-4 text-sm',
  lg: 'h-12 gap-2 rounded-xl px-5 text-base',
  xl: 'h-16 gap-3 rounded-2xl px-6 text-lg',
  icon: 'h-10 w-10 rounded-xl',
  'icon-sm': 'h-8 w-8 rounded-lg',
}

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  icon: Icon,
  className = '',
  children,
  disabled,
  type = 'button',
  ...props
}) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      className={`inline-flex select-none items-center whitespace-nowrap justify-center font-semibold transition active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50 ${VARIANTES[variant]} ${TAMANOS[size]} ${className}`}
      {...props}
    >
      {loading ? (
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
      ) : (
        Icon && <Icon className={size === 'xl' ? 'h-6 w-6' : 'h-4 w-4'} aria-hidden />
      )}
      {children}
    </button>
  )
}
