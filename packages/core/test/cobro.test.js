import assert from 'node:assert/strict'
import { test } from 'node:test'
import * as cobro from '../src/dominio/cobro.js'

const OPCIONES = ['Efectivo', 'Transferencia', 'Tarjeta', 'QR', 'Cuenta corriente']
const abrir = (totalCentavos = 1000000) => cobro.abrir({ totalCentavos, opciones: OPCIONES })
const aplicar = (e, ...acciones) => acciones.reduce(cobro.reducir, e)
const monto = (texto) => ({ tipo: 'escribir', texto })

test('aCentavos entiende los formatos argentinos y rechaza lo inválido', () => {
  assert.equal(cobro.aCentavos('1500'), 150000)
  assert.equal(cobro.aCentavos('1500.5'), 150050)
  assert.equal(cobro.aCentavos('1.500,50'), 150050)
  assert.equal(cobro.aCentavos('1500,5'), 150050)
  assert.equal(cobro.aCentavos(' 0,10 '), 10)
  assert.equal(cobro.aCentavos(''), null)
  assert.equal(cobro.aCentavos('abc'), null)
  assert.equal(cobro.aCentavos('12,345'), null)
  assert.equal(cobro.aMonto(150050), '1500.50')
})

test('las teclas 1 a 5 eligen el medio; fuera de rango no hacen nada', () => {
  let e = abrir()
  assert.equal(e.medio, 'Efectivo')
  e = aplicar(e, { tipo: 'medio', indice: 3 })
  assert.equal(e.medio, 'Tarjeta')
  assert.equal(aplicar(e, { tipo: 'medio', indice: 9 }).medio, 'Tarjeta')
  assert.equal(aplicar(e, { tipo: 'medio', metodo: 'QR' }).medio, 'QR')
  assert.equal(aplicar(e, { tipo: 'medio', metodo: 'Bitcoin' }).medio, 'Tarjeta')
  // Si el medio no está habilitado (p. ej. sin QR), la tecla correspondiente no existe
  assert.equal(aplicar(cobro.abrir({ totalCentavos: 100, opciones: ['Efectivo', 'Tarjeta'] }), { tipo: 'medio', indice: 3 }).medio, 'Efectivo')
})

test('Enter sin monto cobra todo en el medio elegido', () => {
  const e = aplicar(abrir(500000), { tipo: 'medio', indice: 2 }, { tipo: 'confirmar' })
  assert.deepEqual(e.pagos, [{ metodo: 'Transferencia', centavos: 500000 }])
  assert.equal(cobro.completo(e), true)
  assert.equal(cobro.restante(e), 0)
  assert.deepEqual(cobro.cuerpoDePagos(e), { metodo_pago: 'Transferencia' })
})

test('efectivo con un monto mayor: se cobra lo que falta y se calcula el vuelto', () => {
  const e = aplicar(abrir(480050), monto('5000'), { tipo: 'confirmar' })
  assert.deepEqual(e.pagos, [{ metodo: 'Efectivo', centavos: 480050 }]) // el pago es neto
  assert.equal(cobro.vueltoCentavos(e), 19950)
  assert.equal(cobro.listoParaConfirmar(e), true)
})

test('la vista previa del vuelto aparece mientras se tipea', () => {
  const e = aplicar(abrir(480050), monto('5000'))
  assert.equal(cobro.vueltoPrevio(e), 19950)
  assert.equal(cobro.vueltoPrevio(aplicar(e, { tipo: 'medio', indice: 3 })), 0) // solo en efectivo
  assert.equal(cobro.vueltoPrevio(aplicar(e, monto('100'))), 0)
})

test('pago mixto: 1, 5000, Tab, 2, Enter', () => {
  let e = aplicar(abrir(1250000), { tipo: 'medio', indice: 1 }, monto('5000'), { tipo: 'agregar_medio' })
  assert.deepEqual(e.pagos, [{ metodo: 'Efectivo', centavos: 500000 }])
  assert.equal(cobro.restante(e), 750000)
  assert.equal(e.medio, 'Transferencia') // el siguiente medio disponible
  e = aplicar(e, { tipo: 'medio', indice: 2 }, { tipo: 'confirmar' }) // Enter: el resto
  assert.deepEqual(e.pagos, [
    { metodo: 'Efectivo', centavos: 500000 },
    { metodo: 'Transferencia', centavos: 750000 },
  ])
  assert.equal(cobro.completo(e), true)
  assert.deepEqual(cobro.cuerpoDePagos(e), {
    pagos: [{ metodo_pago: 'Efectivo', monto: '5000.00' }, { metodo_pago: 'Transferencia', monto: '7500.00' }],
  })
})

test('Tab con un monto que cubre todo no agrega otro medio', () => {
  const e = aplicar(abrir(100000), monto('1000'), { tipo: 'agregar_medio' })
  assert.deepEqual(e.pagos, [])
  const f = aplicar(abrir(100000), monto('200'), { tipo: 'agregar_medio' })
  assert.equal(f.pagos.length, 1)
})

test('un medio que no es efectivo no puede pasarse del total (no hay vuelto)', () => {
  const e = aplicar(abrir(100000), { tipo: 'medio', indice: 3 }, monto('1500'), { tipo: 'confirmar' })
  assert.deepEqual(e.pagos, [])
  assert.equal(e.aviso.tipo, 'excede_total')
  assert.equal(e.aviso.falta, 100000)
})

test('montos inválidos o en cero se rechazan', () => {
  assert.equal(aplicar(abrir(), monto('1.2.3'), { tipo: 'confirmar' }).aviso.tipo, 'monto_invalido')
  assert.equal(aplicar(abrir(), monto('0'), { tipo: 'confirmar' }).aviso.tipo, 'monto_invalido')
  // Solo entran dígitos y separadores
  assert.equal(aplicar(abrir(), monto('12a3-')).buffer, '123')
})

test('la cuenta corriente exige un cliente para confirmar', () => {
  let e = aplicar(abrir(300000), { tipo: 'medio', indice: 5 }, { tipo: 'confirmar' })
  assert.equal(cobro.requiereCliente(e), true)
  assert.equal(cobro.completo(e), true)
  assert.equal(cobro.listoParaConfirmar(e), false)
  e = aplicar(e, { tipo: 'cliente', clienteId: 7 })
  assert.equal(cobro.listoParaConfirmar(e), true)
  assert.deepEqual(cobro.cuerpoDePagos(e), { cliente_id: 7, metodo_pago: 'Cuenta corriente' })
})

test('parte en efectivo y el resto a cuenta corriente', () => {
  const e = aplicar(abrir(1000000), monto('4000'), { tipo: 'agregar_medio' }, { tipo: 'medio', indice: 5 },
    { tipo: 'confirmar' }, { tipo: 'cliente', clienteId: 3 })
  assert.deepEqual(cobro.cuerpoDePagos(e), {
    cliente_id: 3,
    pagos: [{ metodo_pago: 'Efectivo', monto: '4000.00' }, { metodo_pago: 'Cuenta corriente', monto: '6000.00' }],
  })
})

test('quitar un pago reabre el cobro y recalcula lo recibido', () => {
  let e = aplicar(abrir(1000000), monto('4000'), { tipo: 'agregar_medio' }, { tipo: 'confirmar' })
  assert.equal(cobro.completo(e), true)
  e = aplicar(e, { tipo: 'quitar_pago', indice: 1 })
  assert.equal(cobro.completo(e), false)
  assert.equal(cobro.restante(e), 600000)
  e = aplicar(e, { tipo: 'quitar_pago', indice: 0 })
  assert.deepEqual([e.pagos, e.recibidoEfectivo], [[], 0])
})

test('no se pueden agregar más de 5 medios', () => {
  let e = abrir(1000000)
  for (let i = 0; i < 4; i++) e = aplicar(e, monto('100'), { tipo: 'medio', indice: i + 1 }, { tipo: 'agregar_medio' })
  assert.equal(e.pagos.length, 4)
  e = aplicar(e, { tipo: 'medio', indice: 5 }, monto('100'), { tipo: 'confirmar' })
  assert.equal(e.aviso.tipo, 'max_pagos') // el quinto tiene que cubrir lo que falta
  e = aplicar(e, monto(''), { tipo: 'confirmar' })
  assert.equal(e.pagos.length, 5)
  assert.equal(cobro.completo(e), true)
})

test('reiniciar vuelve al principio', () => {
  const e = aplicar(abrir(100000), monto('500'), { tipo: 'confirmar' }, { tipo: 'reiniciar' })
  assert.deepEqual(e, abrir(100000))
})

test('los medios que llegan después del servidor reemplazan a los de arranque', () => {
  let e = cobro.abrir({ totalCentavos: 100000, opciones: ['Efectivo'] })
  e = aplicar(e, { tipo: 'opciones', opciones: ['Efectivo', 'Tarjeta', 'Cuenta corriente'] })
  assert.deepEqual(e.opciones, ['Efectivo', 'Tarjeta', 'Cuenta corriente'])
  assert.equal(aplicar(e, { tipo: 'medio', indice: 3 }).medio, 'Cuenta corriente')
  // Si el medio elegido ya no existe, vuelve al primero
  const f = aplicar(aplicar(e, { tipo: 'medio', indice: 2 }), { tipo: 'opciones', opciones: ['Efectivo'] })
  assert.equal(f.medio, 'Efectivo')
})
