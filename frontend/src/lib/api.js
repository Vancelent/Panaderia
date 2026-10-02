import axios from 'axios'

const CSRF_COOKIE = 'panaderia_csrf'
const CSRF_HEADER = 'X-CSRF-Token'
const METODOS_SEGUROS = new Set(['get', 'head', 'options'])
// En producción el servidor antepone "__Host-" al nombre (COOKIE_PREFIX): se acepta con o sin él,
// así el mismo build sirve en desarrollo y en producción.
const PREFIJOS_COOKIE = ['__Host-', '']

function leerCookie(nombre) {
  for (const prefijo of PREFIJOS_COOKIE) {
    const completo = `${prefijo}${nombre}`
    const par = document.cookie.split('; ').find((c) => c.startsWith(`${completo}=`))
    if (par) return decodeURIComponent(par.slice(completo.length + 1))
  }
  return null
}

// La sesión viaja en una cookie httpOnly que JavaScript no puede leer.
// Solo leemos la cookie CSRF para reenviarla como header (double-submit).
export const api = axios.create({
  baseURL: '/api/v1',
  withCredentials: true,
  timeout: 15000,
  // estado=a&estado=b (lo que espera FastAPI), no estado[]=a
  paramsSerializer: { indexes: null },
})

api.interceptors.request.use((config) => {
  if (!METODOS_SEGUROS.has((config.method || 'get').toLowerCase())) {
    const token = leerCookie(CSRF_COOKIE)
    if (token) config.headers[CSRF_HEADER] = token
  }
  return config
})

api.interceptors.response.use(
  (res) => res,
  (error) => {
    const url = error.config?.url || ''
    if (error.response?.status === 401 && !url.startsWith('/auth/')) {
      // La sesión venció o fue revocada: AuthProvider redirige al login
      window.dispatchEvent(new Event('auth:expired'))
    }
    return Promise.reject(error)
  },
)

/** Mensaje legible a partir de un error de la API ({error: {message, details}}). */
export function mensajeError(err, porDefecto = 'Ocurrió un error. Intentá de nuevo.') {
  if (!err) return porDefecto
  if (err.code === 'ECONNABORTED') return 'El servidor tardó demasiado en responder.'
  if (!err.response) return 'Sin conexión con el servidor.'
  const e = err.response.data?.error
  if (!e) return porDefecto
  if (e.code === 'validation_error' && Array.isArray(e.details) && e.details.length) {
    return e.details.map((d) => (d.campo ? `${d.campo}: ${d.mensaje}` : d.mensaje)).join(' · ')
  }
  return e.message || porDefecto
}

export const get = (url, params) => api.get(url, { params }).then((r) => r.data)
export const post = (url, body) => api.post(url, body).then((r) => r.data)
export const patch = (url, body) => api.patch(url, body).then((r) => r.data)
export const put = (url, body) => api.put(url, body).then((r) => r.data)
