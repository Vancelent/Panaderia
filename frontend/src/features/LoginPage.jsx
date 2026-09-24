import { useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { Eye, EyeOff, Wheat } from 'lucide-react'
import { useAuth } from '../auth/context'
import { Button } from '../components/ui/Button'
import { Field, Input } from '../components/ui/Field'
import { PantallaCarga } from '../components/ui/Spinner'
import { mensajeError } from '../lib/api'
import { inicioPorRol } from '../lib/roles'

export default function LoginPage() {
  const { user, loading, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [verPass, setVerPass] = useState(false)
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)

  if (loading) return <PantallaCarga />
  if (user) return <Navigate to={inicioPorRol(user.rol)} replace />

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
    <div className="flex min-h-dvh items-center justify-center bg-gradient-to-br from-brand-50 via-stone-100 to-stone-200 p-4 dark:from-stone-950 dark:via-stone-950 dark:to-brand-950/40">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center text-center">
          <div className="mb-4 grid h-16 w-16 place-items-center rounded-2xl bg-brand-600 text-white shadow-lg shadow-brand-600/30">
            <Wheat className="h-8 w-8" />
          </div>
          <h1 className="text-2xl font-extrabold tracking-tight">Panadería</h1>
          <p className="text-sm text-stone-500">Ingresá con tu usuario</p>
        </div>

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
      </div>
    </div>
  )
}
