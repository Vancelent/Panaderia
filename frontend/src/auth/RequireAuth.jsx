import { Navigate, useLocation } from 'react-router-dom'
import { inicioPorRol } from '../lib/roles'
import { PantallaCarga } from '../components/ui/Spinner'
import { useAuth } from './context'

/** Protege rutas por sesión y rol. La autorización real la hace el backend. */
export function RequireAuth({ roles, children }) {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) return <PantallaCarga />
  if (!user) return <Navigate to="/login" replace state={{ desde: location.pathname }} />
  if (roles && !roles.includes(user.rol)) return <Navigate to={inicioPorRol(user.rol)} replace />
  return children
}
