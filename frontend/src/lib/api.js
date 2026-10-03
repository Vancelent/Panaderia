import axios from 'axios'
import { estrategiaCookies, instalarSesion, mensajeError } from '@panaderia/core/api'
import { pedirReautenticacion } from './reauth'

function leerCookie(nombre) {
  const par = document.cookie.split('; ').find((c) => c.startsWith(`${nombre}=`))
  return par ? decodeURIComponent(par.slice(nombre.length + 1)) : null
}

// La sesión viaja en una cookie httpOnly que JavaScript no puede leer.
// Solo leemos la cookie CSRF para reenviarla como header (double-submit). En producción el servidor le
// antepone "__Host-" (COOKIE_PREFIX): el build tiene que saberlo (VITE_COOKIE_PREFIX). El prefijo es
// explícito y no "el que aparezca": en una misma máquina pueden convivir cookies de dos instalaciones
// (p. ej. desarrollo y una prueba de producción en localhost) y elegir mal manda un CSRF equivocado.
const PREFIJO_COOKIES = import.meta.env.VITE_COOKIE_PREFIX ?? ''
export const api = axios.create({
  baseURL: '/api/v1',
  withCredentials: true,
  timeout: 15000,
  // estado=a&estado=b (lo que espera FastAPI), no estado[]=a
  paramsSerializer: { indexes: null },
})

// La lógica de sesión (CSRF, 401, reautenticación) es la del paquete compartido con la app móvil
// (packages/core): acá solo se le dice cómo leer cookies y cómo mostrar el diálogo de confirmación.
instalarSesion(api, estrategiaCookies({ leerCookie, prefijos: [PREFIJO_COOKIES] }), {
  // La sesión venció o fue revocada: AuthProvider redirige al login
  alSesionExpirada: () => window.dispatchEvent(new Event('auth:expired')),
  // Gestión sensible con una sesión de PIN o vieja: se pide confirmar y se repite lo que se estaba haciendo
  pedirReautenticacion,
})

/** Mensaje legible a partir de un error de la API ({error: {message, details}}). */
export { mensajeError }

export const get = (url, params) => api.get(url, { params }).then((r) => r.data)
export const post = (url, body) => api.post(url, body).then((r) => r.data)
export const patch = (url, body) => api.patch(url, body).then((r) => r.data)
export const put = (url, body) => api.put(url, body).then((r) => r.data)
export const del = (url) => api.delete(url).then((r) => r.data)
