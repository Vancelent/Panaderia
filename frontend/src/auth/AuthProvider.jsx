import { useCallback, useEffect, useMemo } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { qk } from '../lib/queries'
import { AuthContext } from './context'

async function fetchMe() {
  try {
    return (await api.get('/auth/me')).data
  } catch (err) {
    if (err.response?.status === 401) return null
    throw err
  }
}

// Borra la caché de datos del usuario anterior sin tocar la query de sesión,
// que AuthProvider sigue observando (qc.clear() la dejaría huérfana).
function limpiarDatos(qc) {
  qc.removeQueries({ predicate: (q) => q.queryKey[0] !== qk.me[0] })
}

export function AuthProvider({ children }) {
  const qc = useQueryClient()
  const { data: user, isLoading, isError, refetch } = useQuery({
    queryKey: qk.me,
    queryFn: fetchMe,
    staleTime: Infinity,
    retry: 1,
  })

  const login = useCallback(
    async (username, password) => {
      const { data } = await api.post('/auth/login', { username, password })
      limpiarDatos(qc)
      qc.setQueryData(qk.me, data)
      return data
    },
    [qc],
  )

  const logout = useCallback(async () => {
    try {
      await api.post('/auth/logout')
    } finally {
      qc.setQueryData(qk.me, null)
      limpiarDatos(qc)
    }
  }, [qc])

  // Cualquier 401 de la API (token vencido/revocado) cierra la sesión local
  useEffect(() => {
    const onExpired = () => {
      qc.setQueryData(qk.me, null)
      limpiarDatos(qc)
    }
    window.addEventListener('auth:expired', onExpired)
    return () => window.removeEventListener('auth:expired', onExpired)
  }, [qc])

  const value = useMemo(
    () => ({ user: user ?? null, loading: isLoading, error: isError, retry: refetch, login, logout }),
    [user, isLoading, isError, refetch, login, logout],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
