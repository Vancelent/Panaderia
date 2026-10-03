import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { ShieldCheck } from 'lucide-react'
import { Button } from '../components/ui/Button'
import { Field, Input } from '../components/ui/Field'
import { Modal } from '../components/ui/Modal'
import { useToast } from '../components/ui/toast'
import { api, mensajeError } from '../lib/api'
import { useMetodosIngreso } from '../lib/queries'
import { useAuth } from './context'
import { MENSAJES_GOOGLE } from './mensajes'

/**
 * Confirmar la identidad para la gestión sensible (docs/rfc-001 §2.4).
 *
 * Una sesión con PIN, o una iniciada hace más de 15 minutos, recibe `401 reautenticacion_requerida` en
 * cambiar precios, usuarios, ajustes, etc. api.js pide acá la confirmación y, si sale bien, repite lo que se
 * estaba haciendo: la persona no pierde la pantalla. Con Google se vuelve a la misma ruta.
 */
export default function ReautenticacionDialog() {
  const { user, actualizarSesion } = useAuth()
  const toast = useToast()
  const metodos = useMetodosIngreso()
  const location = useLocation()
  const navigate = useNavigate()
  const [abierto, setAbierto] = useState(false)
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)
  const promesa = useRef(null)

  useEffect(() => {
    const onReauth = (e) => {
      promesa.current = e.detail
      setPassword('')
      setError('')
      setAbierto(true)
    }
    window.addEventListener('auth:reauth', onReauth)
    return () => window.removeEventListener('auth:reauth', onReauth)
  }, [])

  // Si volvimos de Google con un error (otra cuenta, cancelada…), se muestra y se limpia la URL
  useEffect(() => {
    const params = new URLSearchParams(location.search)
    const codigo = params.get('reauth_error')
    if (!codigo) return
    toast.error(MENSAJES_GOOGLE[codigo] ?? 'No se pudo confirmar tu identidad con Google.')
    params.delete('reauth_error')
    navigate({ pathname: location.pathname, search: params.toString() }, { replace: true })
  }, [location.search, location.pathname, navigate, toast])

  const cerrar = useCallback((resultado) => {
    setAbierto(false)
    const p = promesa.current
    promesa.current = null
    if (!p) return
    if (resultado === 'ok') p.resolve()
    else p.reject(new Error('Reautenticación cancelada'))
  }, [])

  if (!user) return null

  const confirmar = async (e) => {
    e.preventDefault()
    setEnviando(true)
    setError('')
    try {
      const { data } = await api.post('/auth/reautenticacion', { password })
      actualizarSesion(data)
      cerrar('ok')
    } catch (err) {
      setError(mensajeError(err, 'No se pudo confirmar la contraseña.'))
      setPassword('')
    } finally {
      setEnviando(false)
    }
  }

  return (
    <Modal
      open={abierto}
      onClose={() => cerrar('cancelar')}
      title="Confirmá que sos vos"
      description="Esta acción necesita que confirmes tu identidad. No perdés lo que estabas haciendo."
      size="sm"
    >
      <form onSubmit={confirmar} className="space-y-4" noValidate>
        <div className="flex items-center gap-3 rounded-xl bg-stone-100 px-3 py-2.5 text-sm dark:bg-stone-800">
          <ShieldCheck className="h-5 w-5 shrink-0 text-brand-600" />
          <span>
            Sesión de <strong>{user.nombre || user.username}</strong>
            {user.sesion?.metodo === 'pin' && ' (ingresaste con PIN)'}
          </span>
        </div>
        {error && (
          <div role="alert" className="rounded-xl bg-red-50 px-3 py-2.5 text-sm font-medium text-red-700 dark:bg-red-950/50 dark:text-red-300">
            {error}
          </div>
        )}
        <Field label="Tu contraseña">
          {(id) => (
            <Input
              id={id}
              type="password"
              autoComplete="current-password"
              autoFocus
              maxLength={72}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          )}
        </Field>
        <div className="flex flex-wrap justify-end gap-2">
          <Button type="button" variant="ghost" onClick={() => cerrar('cancelar')}>
            Cancelar
          </Button>
          <Button type="submit" loading={enviando} disabled={!password}>
            Confirmar
          </Button>
        </div>
        {metodos.data?.google && (
          <div className="border-t border-stone-200 pt-3 dark:border-stone-800">
            <Button
              type="button"
              variant="secondary"
              className="w-full"
              onClick={() => {
                // Navegación completa: Google pide volver a autenticar y vuelve a esta misma pantalla
                const volver = encodeURIComponent(location.pathname)
                window.location.href = `/api/v1/auth/google/reautenticacion?volver=${volver}`
              }}
            >
              Confirmar con Google
            </Button>
          </div>
        )}
      </form>
    </Modal>
  )
}
