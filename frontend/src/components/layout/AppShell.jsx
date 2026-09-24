import { Suspense, useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { LogOut, Menu, Monitor, Moon, Sun, Wheat, X } from 'lucide-react'
import { useAuth } from '../../auth/context'
import { NAV } from '../../lib/roles'
import { useTheme } from '../../lib/theme'
import { PantallaCarga } from '../ui/Spinner'

const TEMAS = [
  { value: 'light', icon: Sun, label: 'Claro' },
  { value: 'dark', icon: Moon, label: 'Oscuro' },
  { value: 'system', icon: Monitor, label: 'Sistema' },
]

function Marca() {
  return (
    <div className="flex items-center gap-2.5">
      <div className="grid h-9 w-9 place-items-center rounded-xl bg-brand-600 text-white shadow-sm">
        <Wheat className="h-5 w-5" />
      </div>
      <div className="leading-tight">
        <p className="text-sm font-extrabold tracking-tight">Panadería</p>
        <p className="text-[11px] font-medium text-stone-500">Gestión y caja</p>
      </div>
    </div>
  )
}

function Navegacion({ items, onNavigate }) {
  return (
    <nav className="flex flex-col gap-0.5" aria-label="Principal">
      {items.map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/admin'}
          onClick={onNavigate}
          className={({ isActive }) =>
            `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition ${
              isActive
                ? 'bg-brand-50 text-brand-800 dark:bg-brand-950/60 dark:text-brand-200'
                : 'text-stone-600 hover:bg-stone-100 hover:text-stone-900 dark:text-stone-400 dark:hover:bg-stone-800 dark:hover:text-white'
            }`
          }
        >
          <Icon className="h-5 w-5 shrink-0" />
          {label}
        </NavLink>
      ))}
    </nav>
  )
}

function PieUsuario() {
  const { user, logout } = useAuth()
  const [tema, setTema] = useTheme()
  const navigate = useNavigate()
  return (
    <div className="space-y-3 border-t border-stone-200 pt-3 dark:border-stone-800">
      <div className="flex rounded-xl bg-stone-100 p-1 dark:bg-stone-800" role="radiogroup" aria-label="Tema">
        {TEMAS.map(({ value, icon: Icon, label }) => (
          <button
            key={value}
            role="radio"
            aria-checked={tema === value}
            title={label}
            onClick={() => setTema(value)}
            className={`flex flex-1 justify-center rounded-lg py-1.5 ${
              tema === value ? 'bg-white shadow-sm dark:bg-stone-950' : 'text-stone-500'
            }`}
          >
            <Icon className="h-4 w-4" />
          </button>
        ))}
      </div>
      <div className="flex items-center gap-3 px-1">
        <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-stone-200 text-sm font-bold uppercase dark:bg-stone-700">
          {user.username.slice(0, 2)}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold">{user.nombre || user.username}</p>
          <p className="text-xs text-stone-500">{user.rol}</p>
        </div>
        <button
          onClick={async () => {
            await logout()
            navigate('/login', { replace: true })
          }}
          className="rounded-lg p-2 text-stone-500 hover:bg-stone-100 hover:text-red-600 dark:hover:bg-stone-800"
          title="Cerrar sesión"
          aria-label="Cerrar sesión"
        >
          <LogOut className="h-5 w-5" />
        </button>
      </div>
    </div>
  )
}

export function AppShell() {
  const { user } = useAuth()
  const [abierto, setAbierto] = useState(false)
  const items = NAV.filter((n) => n.roles.includes(user.rol))

  return (
    <div className="flex min-h-dvh">
      {/* Barra lateral fija en escritorio */}
      <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col gap-6 border-r border-stone-200 bg-white p-4 dark:border-stone-800 dark:bg-stone-900 lg:flex">
        <Marca />
        <div className="scrollbar-thin -mx-1 flex-1 overflow-y-auto px-1">
          <Navegacion items={items} />
        </div>
        <PieUsuario />
      </aside>

      {/* Cajón en móvil / tablet */}
      {abierto && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 animate-fade-in bg-stone-950/50" onClick={() => setAbierto(false)} />
          <aside className="relative flex h-full w-72 animate-slide-up flex-col gap-6 bg-white p-4 dark:bg-stone-900">
            <div className="flex items-center justify-between">
              <Marca />
              <button onClick={() => setAbierto(false)} className="rounded-lg p-2" aria-label="Cerrar menú">
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto">
              <Navegacion items={items} onNavigate={() => setAbierto(false)} />
            </div>
            <PieUsuario />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-stone-200 bg-white/90 px-4 backdrop-blur dark:border-stone-800 dark:bg-stone-900/90 lg:hidden">
          <button onClick={() => setAbierto(true)} className="-ml-2 rounded-lg p-2" aria-label="Abrir menú">
            <Menu className="h-5 w-5" />
          </button>
          <Marca />
        </header>
        <main className="flex-1 p-4 sm:p-6">
          <Suspense fallback={<PantallaCarga />}>
            <Outlet />
          </Suspense>
        </main>
      </div>
    </div>
  )
}
