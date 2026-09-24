const dinero = new Intl.NumberFormat('es-AR', {
  style: 'currency',
  currency: 'ARS',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})
const dineroCorto = new Intl.NumberFormat('es-AR', {
  style: 'currency',
  currency: 'ARS',
  notation: 'compact',
  maximumFractionDigits: 1,
})
const numero = new Intl.NumberFormat('es-AR', { maximumFractionDigits: 3 })

export const fmtDinero = (v) => dinero.format(Number(v) || 0)
export const fmtDineroCorto = (v) => dineroCorto.format(Number(v) || 0)
export const fmtNumero = (v) => numero.format(Number(v) || 0)

export const fmtFecha = (iso) =>
  new Date(iso).toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: 'numeric' })

export const fmtFechaHora = (iso) =>
  new Date(iso).toLocaleString('es-AR', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  })

export const fmtHora = (iso) =>
  new Date(iso).toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })

/** "Hoy 16:30", "Mañana 09:00", "vie 12/09 10:00" */
export function fmtEntrega(iso) {
  const d = new Date(iso)
  const hoy = new Date()
  const inicio = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime()
  const dias = Math.round((inicio(d) - inicio(hoy)) / 86_400_000)
  const hora = fmtHora(iso)
  if (dias === 0) return `Hoy ${hora}`
  if (dias === 1) return `Mañana ${hora}`
  if (dias === -1) return `Ayer ${hora}`
  return `${d.toLocaleDateString('es-AR', { weekday: 'short', day: '2-digit', month: '2-digit' })} ${hora}`
}

/** Fecha local en formato YYYY-MM-DD (para inputs y parámetros de la API). */
export function isoLocal(d = new Date()) {
  const z = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}`
}

export function sumarDias(d, n) {
  const r = new Date(d)
  r.setDate(r.getDate() + n)
  return r
}
