import assert from 'node:assert/strict'
import { test } from 'node:test'
import * as caja from '../src/dominio/caja.js'

const P = (id, nombre, extra = {}) => ({
  id, nombre, categoria: null, codigo: null, precio_venta: 100, stock_disponible: 10, activo: true, ...extra,
})
const productos = [
  P(1, 'Medialuna', { codigo: '101', precio_venta: 80.5, stock_disponible: 24, categoria: 'Facturas' }),
  P(2, 'Pan francés', { codigo: '201', precio_venta: 120, stock_disponible: 5, categoria: 'Panes' }),
  P(3, 'Pan lactal', { codigo: '202', precio_venta: 350, stock_disponible: 0, categoria: 'Panes' }),
  P(4, 'Dado de baja', { activo: false }),
]
const aplicar = (...acciones) => acciones.reduce(caja.reducir, caja.reducir(caja.estadoInicial(), { tipo: 'catalogo', productos }))
const escribir = (texto) => ({ tipo: 'escribir', texto })
const enter = { tipo: 'enter' }

test('el catálogo deja fuera los productos dados de baja', () => {
  const e = aplicar()
  assert.equal(e.catalogo.length, 3)
  assert.equal(caja.resultados(e).length, 3)
})

test('Enter agrega el primer resultado y deja el buscador limpio', () => {
  const e = aplicar(escribir('med'), enter)
  assert.deepEqual(e.lineas, [{ productoId: 1, cantidad: 1 }])
  assert.equal(e.consulta, '')
  assert.equal(e.aviso.tipo, 'agregado')
})

test('"12*med" agrega 12 medialunas', () => {
  const e = aplicar(escribir('12*med'), enter)
  assert.deepEqual(e.lineas, [{ productoId: 1, cantidad: 12 }])
  assert.equal(caja.anuncio(e), 'Agregado: 12 Medialuna')
  assert.equal(caja.totalCentavos(e), 12 * 8050)
})

test('el multiplicador del buscador tiene prioridad sobre el de los botones y se reinicia', () => {
  let e = aplicar({ tipo: 'fijar_multiplicador', n: 6 }, escribir('pan fr'), enter)
  assert.equal(e.lineas[0].cantidad, 5) // pidió 6, pero solo hay 5
  e = aplicar({ tipo: 'fijar_multiplicador', n: 6 }, escribir('2*med'), enter)
  assert.equal(e.lineas[0].cantidad, 2)
  assert.equal(e.multiplicador, 1)
})

test('un código numérico más Enter agrega por código exacto, aunque no sea el primer resultado', () => {
  const e = aplicar(escribir('201'), enter)
  assert.deepEqual(e.lineas, [{ productoId: 2, cantidad: 1 }])
  const m = aplicar(escribir('3*201'), enter) // multiplicador + código
  assert.deepEqual(m.lineas, [{ productoId: 2, cantidad: 3 }])
})

test('↑ y ↓ mueven la selección sin salirse de los resultados', () => {
  let e = aplicar(escribir('pan'))
  assert.equal(e.seleccion, 0)
  e = caja.reducir(e, { tipo: 'mover', delta: 1 })
  assert.equal(e.seleccion, 1)
  e = caja.reducir(e, { tipo: 'mover', delta: 5 })
  assert.equal(e.seleccion, 1) // hay 2 resultados
  e = caja.reducir(e, { tipo: 'mover', delta: -9 })
  assert.equal(e.seleccion, 0)
  // Enter agrega el resaltado: el segundo resultado es el pan lactal, que está agotado
  e = caja.reducir(caja.reducir(e, { tipo: 'mover', delta: 1 }), enter)
  assert.deepEqual([e.lineas, e.aviso.tipo, e.aviso.producto.id], [[], 'sin_stock', 3])
  e = caja.reducir(caja.reducir(aplicar(escribir('pan')), { tipo: 'mover', delta: -1 }), enter)
  assert.equal(e.lineas[0].productoId, 2)
})

test('no se vende más de lo disponible: se topa y se avisa', () => {
  let e = aplicar(escribir('20*pan fr'), enter)
  assert.deepEqual(e.lineas, [{ productoId: 2, cantidad: 5 }])
  assert.equal(e.aviso.tipo, 'tope')
  assert.match(caja.anuncio(e), /Solo se agregaron 5 de Pan francés/)
  e = caja.reducir(caja.reducir(e, escribir('pan fr')), enter) // ya no queda nada
  assert.equal(e.lineas[0].cantidad, 5)
  assert.equal(e.aviso.tipo, 'sin_stock')
  // Un producto agotado no se agrega
  e = aplicar(escribir('lactal'), enter)
  assert.deepEqual(e.lineas, [])
  assert.equal(e.aviso.tipo, 'sin_stock')
})

test('agregar el mismo producto suma a la línea existente y conserva el orden', () => {
  const e = aplicar(escribir('med'), enter, escribir('pan fr'), enter, escribir('med'), enter)
  assert.deepEqual(e.lineas, [{ productoId: 1, cantidad: 2 }, { productoId: 2, cantidad: 1 }])
  assert.equal(e.lineaSel, 0)
})

test('el ticket: +, − y quitar sobre la línea seleccionada', () => {
  let e = aplicar(escribir('2*med'), enter, escribir('pan fr'), enter)
  assert.equal(e.lineaSel, 1) // la última agregada queda seleccionada
  e = caja.reducir(e, { tipo: 'ticket_mover', delta: -1 })
  e = caja.reducir(e, { tipo: 'ticket_sumar' })
  assert.deepEqual(e.lineas[0], { productoId: 1, cantidad: 3 })
  e = caja.reducir(caja.reducir(e, { tipo: 'ticket_restar' }), { tipo: 'ticket_restar' })
  assert.deepEqual(e.lineas[0], { productoId: 1, cantidad: 1 })
  e = caja.reducir(e, { tipo: 'ticket_restar' }) // llegar a cero quita la línea
  assert.deepEqual(e.lineas, [{ productoId: 2, cantidad: 1 }])
  assert.equal(e.aviso.tipo, 'quitado')
  e = caja.reducir(e, { tipo: 'ticket_quitar' })
  assert.deepEqual(e.lineas, [])
  assert.equal(caja.reducir(e, { tipo: 'ticket_sumar' }), e) // sin líneas no hace nada
})

test('sumar en el ticket no pasa del stock disponible', () => {
  let e = aplicar(escribir('5*pan fr'), enter)
  e = caja.reducir(e, { tipo: 'ticket_sumar' })
  assert.equal(e.lineas[0].cantidad, 5)
  assert.equal(e.aviso.tipo, 'tope')
})

test('fijar_cantidad (táctil) acota al stock y 0 quita la línea', () => {
  let e = aplicar({ tipo: 'agregar', productoId: 2, cantidad: 2 })
  e = caja.reducir(e, { tipo: 'fijar_cantidad', productoId: 2, cantidad: 99 })
  assert.equal(e.lineas[0].cantidad, 5)
  e = caja.reducir(e, { tipo: 'fijar_cantidad', productoId: 2, cantidad: 0 })
  assert.deepEqual(e.lineas, [])
})

test('agregar por toque usa el multiplicador de los botones', () => {
  const e = aplicar({ tipo: 'fijar_multiplicador', n: 12 }, { tipo: 'agregar', productoId: 1 })
  assert.deepEqual(e.lineas, [{ productoId: 1, cantidad: 12 }])
  assert.equal(e.multiplicador, 1)
})

test('el total se calcula en centavos enteros, sin errores de coma flotante', () => {
  const e = aplicar({ tipo: 'agregar', productoId: 1, cantidad: 3 }, { tipo: 'agregar', productoId: 2, cantidad: 2 })
  assert.equal(caja.totalCentavos(e), 3 * 8050 + 2 * 12000)
  assert.equal(caja.unidades(e), 5)
  const raro = caja.reducir(caja.estadoInicial(), { tipo: 'catalogo', productos: [P(9, 'X', { precio_venta: 0.1 + 0.2 })] })
  assert.equal(caja.totalCentavos(caja.reducir(raro, { tipo: 'agregar', productoId: 9, cantidad: 10 })), 300)
})

test('el refresco del catálogo no pierde el ticket ni mueve la selección', () => {
  const base = aplicar(escribir('pan'), { tipo: 'mover', delta: 1 }, { tipo: 'agregar', productoId: 1, cantidad: 2 })
  const antes = caja.resultados(base).map((p) => p.id)
  // Llega el mismo catálogo con otro stock (cada 8 s)
  const refrescado = caja.reducir(base, {
    tipo: 'catalogo', productos: productos.map((p) => ({ ...p, stock_disponible: p.stock_disponible + 3 })),
  })
  assert.equal(refrescado.seleccion, base.seleccion)
  assert.deepEqual(caja.resultados(refrescado).map((p) => p.id), antes)
  assert.deepEqual(refrescado.lineas, [{ productoId: 1, cantidad: 2 }])
})

test('si el stock baja en otra caja, la línea queda marcada como excedida', () => {
  let e = aplicar({ tipo: 'agregar', productoId: 2, cantidad: 4 })
  e = caja.reducir(e, { tipo: 'catalogo', productos: productos.map((p) => (p.id === 2 ? { ...p, stock_disponible: 2 } : p)) })
  assert.equal(caja.lineasDetalladas(e)[0].excede, true)
  assert.deepEqual(caja.itemsParaVenta(e), [{ producto_id: 2, cantidad: 4 }]) // el servidor decide
})

test('sin resultados avisa y no agrega nada', () => {
  const e = aplicar(escribir('xyz'), enter)
  assert.deepEqual(e.lineas, [])
  assert.equal(caja.anuncio(e), 'Sin resultados para xyz')
})

test('categorías y filtro', () => {
  let e = aplicar()
  assert.deepEqual(caja.categorias(e), ['Facturas', 'Panes'])
  e = caja.reducir(e, { tipo: 'categoria', categoria: 'Panes' })
  assert.deepEqual(caja.resultados(e).map((p) => p.id), [2, 3])
})

test('vender y vaciar dejan la caja lista para la próxima venta', () => {
  let e = aplicar({ tipo: 'agregar', productoId: 1, cantidad: 2 })
  assert.deepEqual(caja.reducir(e, { tipo: 'vaciar' }).lineas, [])
  e = caja.reducir(aplicar(escribir('x'), { tipo: 'agregar', productoId: 1, cantidad: 2 }), { tipo: 'vendido' })
  assert.deepEqual([e.lineas, e.consulta, e.multiplicador], [[], '', 1])
})
