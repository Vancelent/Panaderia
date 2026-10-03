import { useEffect, useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { Delete, Eye, EyeOff, KeyRound, Monitor, Wheat } from 'lucide-react'
import { useAuth } from '../auth/context'
import { MENSAJES_GOOGLE } from '../auth/mensajes'
import { Button } from '../components/ui/Button'
import { Field, Input } from '../components/ui/Field'
import { PantallaCarga } from '../components/ui/Spinner'
import { mensajeError } from '../lib/api'
import { useMetodosIngreso } from '../lib/queries'
import { inicioPorRol } from '../lib/roles'

function GoogleLogo() {
  return (
    <svg viewBox="0 0 48 48" className="h-5 w-5" aria-hidden>
      <path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9.1 3.6l6.8-6.8C35.8 2.4 30.3 0 24 0 14.6 0 6.5 5.4 2.6 13.2l7.9 6.1C12.4 13.6 17.7 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.7c-.6 3-2.3 5.5-4.8 7.2l7.6 5.9c4.4-4.1 7-10.1 7-17.6z" />
      <path fill="#FBBC05" d="M10.5 28.7c-.5-1.5-.8-3-.8-4.7s.3-3.2.8-4.7l-7.9-6.1C.9 16.4 0 20.1 0 24s.9 7.6 2.6 10.8l7.9-6.1z" />
      <path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.6-5.9c-2.1 1.4-4.9 2.3-8.3 2.3-6.3 0-11.6-4.1-13.5-9.8l-7.9 6.1C6.5 42.6 14.6 48 24 48z" />
    </svg>
  )
}

export default function LoginPage() {
  const { user, loading } = useAuth()
  const location = useLocation()
  const metodos = useMetodosIngreso()
  const [modo, setModo] = useState(null) // 'pin' | 'password'; null = el que corresponda a este equipo
  const errorGoogle = new URLSearchParams(location.search).get('error')

  if (loading) return <PantallaCarga />
  if (user) return <Navigate to={inicioPorRol(user.rol)} replace />

  const terminal = metodos.data?.terminal
  const actual = modo ?? (terminal ? 'pin' : 'password')

  return (
    <div className="flex min-h-dvh items-center justify-center bg-gradient-to-br from-brand-50 via-stone-100 to-stone-200 p-4 dark:from-stone-950 dark:via-stone-950 dark:to-brand-950/40">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center text-center">
          <div className="mb-4 grid h-16 w-16 place-items-center rounded-2xl bg-brand-600 text-white shadow-lg shadow-brand-600/30">
            <Wheat className="h-8 w-8" />
          </div>
          <h1 className="text-2xl font-extrabold tracking-tight">Panadería</h1>
          <p className="text-sm text-stone-500">
            {actual === 'pin' ? `Elegí tu nombre · ${terminal.nombre}` : 'Ingresá con tu usuario'}
          </p>
        </div>

        {errorGoogle && (
          <div role="alert" className="mb-4 rounded-xl bg-red-50 px-3 py-2.5 text-sm font-medium text-red-700 dark:bg-red-950/50 dark:text-red-300">
            {MENSAJES_GOOGLE[errorGoogle] ?? 'No se pudo iniciar sesión.'}
          </div>
        )}

        {actual === 'pin' ? <IngresoConPin terminal={terminal} /> : <IngresoConPassword />}

        <div className="mt-4 space-y-2">
          {metodos.data?.google && (
            <Button
              variant="secondary"
              size="lg"
              className="w-full"
              onClick={() => {
                // Navegación completa: Google devuelve a /api/v1/auth/google/callback y de ahí a la app
                const destino = location.state?.desde
                window.location.href = `/api/v1/auth/google/inicio${destino ? `?volver=${encodeURIComponent(destino)}` : ''}`
              }}
            >
              <GoogleLogo /> Ingresar con Google
            </Button>
          )}
          {terminal && (
            <Button
              variant="ghost"
              className="w-full"
              icon={actual === 'pin' ? KeyRound : Monitor}
              onClick={() => setModo(actual === 'pin' ? 'password' : 'pin')}
            >
              {actual === 'pin' ? 'Usar usuario y contraseña' : 'Ingresar con PIN'}
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}

function IngresoConPassword() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [verPass, setVerPass] = useState(false)
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)

  const onSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setEnviando(true)
    try {
      const u = await login(username.trim(), password)
      const destino = location.state?.desde
      navigate(destino && destino !== '/login' ? destino : inicioPorRol(u.rol), { replace: true })
    } catch (err) {
      setError(mensajeError(err, 'No se pudo iniciar sesión.'))
      setPassword('')
    } finally {
      setEnviando(false)
    }
  }

  return (
    <form onSubmit={onSubmit} className="card space-y-4 p-6" noValidate>
      {error && (
        <div role="alert" className="rounded-xl bg-red-50 px-3 py-2.5 text-sm font-medium text-red-700 dark:bg-red-950/50 dark:text-red-300">
          {error}
        </div>
      )}
      <Field label="Usuario">
        {(id) => (
          <Input
            id={id}
            autoFocus
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
          />
        )}
      </Field>
      <Field label="Contraseña">
        {(id) => (
          <div className="relative">
            <Input
              id={id}
              type={verPass ? 'text' : 'password'}
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="pr-11"
              required
            />
            <button
              type="button"
              onClick={() => setVerPass((v) => !v)}
              className="absolute inset-y-0 right-0 grid w-11 place-items-center text-stone-400 hover:text-stone-700"
              aria-label={verPass ? 'Ocultar contraseña' : 'Mostrar contraseña'}
            >
              {verPass ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
        )}
      </Field>
      <Button type="submit" size="lg" className="w-full" loading={enviando} disabled={!username || !password}>
        Ingresar
      </Button>
    </form>
  )
}

const TECLAS = ['1', '2', '3', '4', '5', '6', '7', '8', '9']

/** Ingreso con PIN: solo en un equipo registrado (la cookie del terminal la pone el servidor). */
function IngresoConPin({ terminal }) {
  const { loginPin } = useAuth()
  const navigate = useNavigate()
  const [elegido, setElegido] = useState(null)
  const [pin, setPin] = useState('')
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)

  const ingresar = async (valor = pin) => {
    if (valor.length < 4 || enviando) return
    setError('')
    setEnviando(true)
    try {
      const u = await loginPin(elegido.id, valor)
      navigate(inicioPorRol(u.rol), { replace: true })
    } catch (err) {
      setError(mensajeError(err, 'No se pudo ingresar.'))
      setPin('')
    } finally {
      setEnviando(false)
    }
  }

  // El teclado físico también sirve: dígitos, Retroceso y Enter
  useEffect(() => {
    if (!elegido) return undefined
    const onKey = (e) => {
      if (/^\d$/.test(e.key)) setPin((p) => (p.length < 6 ? p + e.key : p))
      else if (e.key === 'Backspace') setPin((p) => p.slice(0, -1))
      else if (e.key === 'Escape') {
        setElegido(null)
        setPin('')
        setError('')
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [elegido])

  if (!elegido) {
    return (
      <div className="card p-4">
        {terminal.usuarios.length === 0 ? (
          <p className="p-4 text-center text-sm text-stone-500">
            Todavía no hay personas con PIN para este equipo. Un administrador puede cargarlo en Usuarios.
          </p>
        ) : (
          <ul className="grid grid-cols-2 gap-2">
            {terminal.usuarios.map((u) => (
              <li key={u.id}>
                <button
                  onClick={() => setElegido(u)}
                  className="flex w-full flex-col items-center gap-2 rounded-2xl border border-stone-200 p-4 text-center transition hover:border-brand-400 hover:bg-brand-50 active:scale-[0.97] dark:border-stone-700 dark:hover:bg-brand-950/40"
                >
                  <span className="grid h-12 w-12 place-items-center rounded-full bg-stone-200 text-lg font-bold uppercase dark:bg-stone-700">
                    {(u.nombre || u.username).slice(0, 2)}
                  </span>
                  <span className="text-sm font-semibold leading-tight">{u.nombre || u.username}</span>
                  <span className="text-xs text-stone-500">{u.rol}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    )
  }

  return (
    <div className="card p-6">
      <div className="mb-4 flex items-center justify-between">
        <p className="font-semibold">{elegido.nombre || elegido.username}</p>
        <Button size="sm" variant="ghost" onClick={() => { setElegido(null); setPin(''); setError('') }}>
          Cambiar
        </Button>
      </div>
      {error && (
        <div role="alert" className="mb-4 rounded-xl bg-red-50 px-3 py-2.5 text-sm font-medium text-red-700 dark:bg-red-950/50 dark:text-red-300">
          {error}
        </div>
      )}
      <div className="mb-5 flex justify-center gap-3" aria-label={`PIN: ${pin.length} dígitos`} role="status">
        {Array.from({ length: 6 }, (_, i) => (
          <span
            key={i}
            className={`h-3.5 w-3.5 rounded-full border-2 ${
              i < pin.length ? 'border-brand-600 bg-brand-600' : 'border-stone-300 dark:border-stone-600'
            } ${i >= 4 && i >= pin.length ? 'opacity-40' : ''}`}
          />
        ))}
      </div>
      <div className="grid grid-cols-3 gap-2">
        {TECLAS.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setPin((p) => (p.length < 6 ? p + t : p))}
            className="h-14 rounded-2xl bg-stone-100 text-xl font-bold transition active:scale-95 hover:bg-stone-200 dark:bg-stone-800 dark:hover:bg-stone-700"
          >
            {t}
          </button>
        ))}
        <button
          type="button"
          onClick={() => setPin((p) => p.slice(0, -1))}
          className="grid h-14 place-items-center rounded-2xl bg-stone-100 transition active:scale-95 hover:bg-stone-200 dark:bg-stone-800 dark:hover:bg-stone-700"
          aria-label="Borrar"
        >
          <Delete className="h-5 w-5" />
        </button>
        <button
          type="button"
          onClick={() => setPin((p) => (p.length < 6 ? p + '0' : p))}
          className="h-14 rounded-2xl bg-stone-100 text-xl font-bold transition active:scale-95 hover:bg-stone-200 dark:bg-stone-800 dark:hover:bg-stone-700"
        >
          0
        </button>
        <button
          type="button"
          disabled={pin.length < 4 || enviando}
          onClick={() => ingresar()}
          className="h-14 rounded-2xl bg-brand-600 text-base font-bold text-white transition active:scale-95 hover:bg-brand-700 disabled:opacity-40"
        >
          {enviando ? '…' : 'Entrar'}
        </button>
      </div>
      <PinEnter pin={pin} onEnter={() => ingresar()} />
    </div>
  )
}

// Enter con el teclado físico (un componente aparte para no recrear el listener con cada dígito)
function PinEnter({ pin, onEnter }) {
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Enter' && pin.length >= 4) {
        e.preventDefault()
        onEnter()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [pin, onEnter])
  return null
}
