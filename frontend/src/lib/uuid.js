/**
 * UUID v4 para identificar operaciones (idempotencia): reenviar la misma operación no la duplica.
 * `crypto.randomUUID` solo existe en contextos seguros (HTTPS o localhost); si la app se abre por
 * HTTP desde otro equipo de la red local, se arma el UUID con `getRandomValues`.
 */
export function nuevoUuid() {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  const b = crypto.getRandomValues(new Uint8Array(16))
  b[6] = (b[6] & 0x0f) | 0x40
  b[8] = (b[8] & 0x3f) | 0x80
  const h = [...b].map((x) => x.toString(16).padStart(2, '0'))
  return `${h.slice(0, 4).join('')}-${h.slice(4, 6).join('')}-${h.slice(6, 8).join('')}-${h.slice(8, 10).join('')}-${h.slice(10).join('')}`
}
