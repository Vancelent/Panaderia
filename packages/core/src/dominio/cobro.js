// Controlador del cobro: lógica pura del pago único o mixto, pensada para el teclado (docs/rfc-001 §6.2).
//
//   1…5 elige el medio · número + Enter fija el monto de ese medio · Tab después de un monto parcial
//   agrega otro medio por el saldo restante · si el monto cubre el total, muestra el vuelto (efectivo)
//
// Los montos se manejan en centavos enteros. El servidor recalcula el total y rechaza pagos que no suman
// (`pagos_no_cuadran`): lo que se calcula acá es solo para mostrar.

export const EFECTIVO = 'Efectivo'
export const CUENTA_CORRIENTE = 'Cuenta corriente'
export const MAX_PAGOS = 5

/** "1.500,50" / "1500.5" / "1500" → 150050 centavos (o null si no es un monto válido). */
export function aCentavos(texto) {
  const limpio = String(texto ?? '').trim().replace(/\s/g, '')
  if (!limpio) return null
  // Si tiene coma, la coma es el decimal y los puntos son miles; si no, el punto es el decimal
  const normal = limpio.includes(',') ? limpio.replace(/\./g, '').replace(',', '.') : limpio
  if (!/^\d+(\.\d{0,2})?$/.test(normal)) return null
  return Math.round(Number(normal) * 100)
}

export const aMonto = (cent) => (cent / 100).toFixed(2)

export function abrir({ totalCentavos, opciones }) {
  return {
    total: totalCentavos,
    opciones, // medios disponibles, en el orden de las teclas 1…5
    pagos: [], // [{ metodo, centavos }] ya confirmados
    medio: opciones[0] ?? EFECTIVO,
    buffer: '', // lo que se está tipeando
    clienteId: null,
    recibidoEfectivo: 0, // lo que entregó el cliente en efectivo (para calcular el vuelto)
    aviso: null,
  }
}

// ---------- Selectores ----------

export const pagado = (e) => e.pagos.reduce((t, p) => t + p.centavos, 0)
export const restante = (e) => Math.max(0, e.total - pagado(e))
export const completo = (e) => e.total > 0 && pagado(e) >= e.total
export const efectivoCobrado = (e) =>
  e.pagos.filter((p) => p.metodo === EFECTIVO).reduce((t, p) => t + p.centavos, 0)
export const vueltoCentavos = (e) => Math.max(0, e.recibidoEfectivo - efectivoCobrado(e))
export const requiereCliente = (e) => e.pagos.some((p) => p.metodo === CUENTA_CORRIENTE)
export const listoParaConfirmar = (e) => completo(e) && (!requiereCliente(e) || e.clienteId != null)

/** Vista previa mientras se tipea: cuánto sería el vuelto si se confirmara el monto actual en efectivo. */
export function vueltoPrevio(e) {
  const monto = aCentavos(e.buffer)
  if (e.medio !== EFECTIVO || monto == null) return 0
  return Math.max(0, monto - restante(e))
}

/** Cuerpo de POST /ventas (sin los ítems): un solo medio por el total, o la lista de pagos. */
export function cuerpoDePagos(e) {
  const cuerpo = {}
  if (requiereCliente(e)) cuerpo.cliente_id = e.clienteId
  if (e.pagos.length === 1) {
    cuerpo.metodo_pago = e.pagos[0].metodo
  } else {
    cuerpo.pagos = e.pagos.map((p) => ({ metodo_pago: p.metodo, monto: aMonto(p.centavos) }))
  }
  return cuerpo
}

// ---------- Reducer ----------

function siguienteMedio(e, pagos) {
  const usados = new Set(pagos.map((p) => p.metodo))
  return e.opciones.find((o) => !usados.has(o)) ?? e.medio
}

/** Confirma el monto del medio actual. Sin monto tipeado, cubre todo lo que falta. */
function confirmarMonto(e, { soloParcial = false } = {}) {
  if (completo(e)) return e
  const falta = restante(e)
  const tipeado = aCentavos(e.buffer)
  if (e.buffer.trim() && tipeado == null) return { ...e, aviso: { tipo: 'monto_invalido' } }
  const monto = tipeado ?? falta
  if (monto <= 0) return { ...e, aviso: { tipo: 'monto_invalido' } }
  if (soloParcial && monto >= falta) return e // Tab solo agrega un medio cuando el monto es parcial
  if (e.pagos.length >= MAX_PAGOS - 1 && monto < falta) return { ...e, aviso: { tipo: 'max_pagos' } }

  let aplicado = monto
  let recibido = e.recibidoEfectivo
  if (monto > falta) {
    if (e.medio !== EFECTIVO) return { ...e, aviso: { tipo: 'excede_total', falta } }
    aplicado = falta // en efectivo se cobra lo que falta y se da vuelto: el pago se guarda neto
  }
  if (e.medio === EFECTIVO) recibido += monto
  const pagos = [...e.pagos, { metodo: e.medio, centavos: aplicado }]
  const nuevo = { ...e, pagos, buffer: '', recibidoEfectivo: recibido, aviso: null }
  return completo(nuevo) ? nuevo : { ...nuevo, medio: siguienteMedio(e, pagos) }
}

export function reducir(e, accion) {
  switch (accion.tipo) {
    case 'medio': {
      // Por posición (la tecla 1…5) o por nombre (un clic)
      const metodo = accion.indice != null ? e.opciones[accion.indice - 1] : accion.metodo
      if (!metodo || !e.opciones.includes(metodo) || completo(e)) return e
      return { ...e, medio: metodo, aviso: null }
    }
    case 'escribir':
      // Solo dígitos y un separador decimal: nada más llega al monto
      return { ...e, buffer: String(accion.texto ?? '').replace(/[^\d.,]/g, ''), aviso: null }
    case 'confirmar':
      return confirmarMonto(e)
    case 'agregar_medio':
      return confirmarMonto(e, { soloParcial: true })
    case 'quitar_pago': {
      const pagos = e.pagos.filter((_, i) => i !== accion.indice)
      const recibido = pagos.filter((p) => p.metodo === EFECTIVO).reduce((t, p) => t + p.centavos, 0)
      // Al quitar un pago, lo "recibido" en efectivo se recalcula con lo que queda
      return {
        ...e,
        pagos,
        recibidoEfectivo: recibido,
        medio: e.pagos[accion.indice]?.metodo ?? e.medio,
        aviso: null,
      }
    }
    case 'opciones': {
      // Los medios habilitados llegan del servidor y pueden cargar después de abrir el cobro
      const medio = accion.opciones.includes(e.medio) ? e.medio : (accion.opciones[0] ?? e.medio)
      return { ...e, opciones: accion.opciones, medio }
    }
    case 'cliente':
      return { ...e, clienteId: accion.clienteId }
    case 'reiniciar':
      return abrir({ totalCentavos: e.total, opciones: e.opciones })
    default:
      return e
  }
}
