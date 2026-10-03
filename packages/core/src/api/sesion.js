// Cliente HTTP con estrategia de sesión inyectable: cookies + CSRF en la web, Bearer en la app.
//
// El paquete no importa axios (cada plataforma trae el suyo): `instalarSesion` recibe la instancia ya
// creada y le agrega los interceptores. Así la lógica de sesión se prueba y se comparte sin dependencias.

export const METODOS_SEGUROS = new Set(['get', 'head', 'options'])
export const CODIGO_REAUTENTICACION = 'reautenticacion_requerida'

/** Web: la sesión viaja en una cookie httpOnly; en escrituras se reenvía la cookie CSRF como encabezado. */
export function estrategiaCookies({
  leerCookie,
  nombreCsrf = 'panaderia_csrf',
  cabeceraCsrf = 'X-CSRF-Token',
  // En producción el servidor antepone "__Host-" al nombre; se acepta con o sin prefijo
  prefijos = ['__Host-', ''],
}) {
  return {
    preparar(config) {
      if (METODOS_SEGUROS.has((config.method || 'get').toLowerCase())) return
      for (const prefijo of prefijos) {
        const token = leerCookie(`${prefijo}${nombreCsrf}`)
        if (token) {
          config.headers[cabeceraCsrf] = token
          return
        }
      }
    },
  }
}

/** App: `Authorization: Bearer`, que no necesita CSRF porque el navegador no lo agrega solo. */
export function estrategiaBearer({ obtenerAccess }) {
  return {
    async preparar(config) {
      const token = await obtenerAccess()
      if (token) config.headers.Authorization = `Bearer ${token}`
    },
  }
}

export const codigoDeError = (error) => error?.response?.data?.error?.code

/**
 * Instala la estrategia y el manejo de errores de sesión:
 * - `401 reautenticacion_requerida`: la gestión sensible pide confirmar la identidad. Se llama a
 *   `pedirReautenticacion()` (que muestra el diálogo) y, si sale bien, se repite la solicitud original.
 * - cualquier otro `401` fuera de /auth/: la sesión venció o fue revocada (`alSesionExpirada`).
 */
export function instalarSesion(api, estrategia, { alSesionExpirada, pedirReautenticacion } = {}) {
  api.interceptors.request.use(async (config) => {
    await estrategia.preparar(config)
    return config
  })

  api.interceptors.response.use(
    (res) => res,
    async (error) => {
      const url = error.config?.url || ''
      if (error.response?.status === 401) {
        if (codigoDeError(error) === CODIGO_REAUTENTICACION && pedirReautenticacion && !error.config.__reintentada) {
          await pedirReautenticacion() // si la persona cancela, rechaza y se propaga el error original
          error.config.__reintentada = true
          return api.request(error.config)
        }
        if (!url.startsWith('/auth/')) alSesionExpirada?.()
      }
      throw error
    },
  )
}

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
