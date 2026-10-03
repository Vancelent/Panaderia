import assert from 'node:assert/strict'
import { test } from 'node:test'
import { buscar, crearIndice, normalizar, parsearConsulta, porCodigo } from '../src/dominio/busqueda.js'

const P = (id, nombre, extra = {}) => ({ id, nombre, categoria: null, codigo: null, precio_venta: 100, stock_disponible: 10, ...extra })
const catalogo = [
  P(1, 'Medialuna de manteca', { codigo: '101', categoria: 'Facturas' }),
  P(2, 'Medialuna de grasa', { codigo: '102', categoria: 'Facturas' }),
  P(3, 'Pan francés', { codigo: '201', categoria: 'Panes' }),
  P(4, 'Pan lactal', { codigo: '202', categoria: 'Panes' }),
  P(5, 'Cañón de dulce de leche', { codigo: '301', categoria: 'Facturas' }),
  P(6, 'Café con leche', { categoria: 'Bebidas' }),
]
const nombres = (lista) => lista.map((p) => p.nombre)

test('normalizar quita acentos y mayúsculas', () => {
  assert.equal(normalizar('  Pan FRANCÉS '), 'pan frances')
  assert.equal(normalizar('Cañón'), 'canon')
  assert.equal(normalizar(null), '')
})

test('busca sin acentos ni mayúsculas', () => {
  const idx = crearIndice(catalogo)
  assert.deepEqual(nombres(buscar(idx, 'FRANCES')), ['Pan francés'])
  assert.deepEqual(nombres(buscar(idx, 'canon')), ['Cañón de dulce de leche'])
  assert.deepEqual(nombres(buscar(idx, 'cafe')), ['Café con leche'])
})

test('el prefijo del nombre va antes que una coincidencia en el medio', () => {
  const idx = crearIndice(catalogo)
  // "leche": aparece en el medio de dos nombres; "le" también es prefijo de "lactal"? no: "la"
  assert.deepEqual(nombres(buscar(idx, 'pan')), ['Pan francés', 'Pan lactal'])
  assert.equal(nombres(buscar(idx, 'med'))[0].startsWith('Medialuna'), true)
})

test('varias palabras: todas tienen que coincidir, en cualquier orden', () => {
  const idx = crearIndice(catalogo)
  assert.deepEqual(nombres(buscar(idx, 'dulce leche')), ['Cañón de dulce de leche'])
  assert.deepEqual(nombres(buscar(idx, 'leche dulce')), ['Cañón de dulce de leche'])
  assert.deepEqual(buscar(idx, 'dulce pan'), [])
})

test('el código exacto va primero y el prefijo de código también encuentra', () => {
  const idx = crearIndice(catalogo)
  assert.equal(buscar(idx, '202')[0].nombre, 'Pan lactal')
  assert.deepEqual(nombres(buscar(idx, '10')), ['Medialuna de grasa', 'Medialuna de manteca'])
  assert.equal(porCodigo(idx, '201').nombre, 'Pan francés')
  assert.equal(porCodigo(idx, '20'), null) // solo coincidencia exacta
  assert.equal(porCodigo(idx, ''), null)
})

test('sin consulta devuelve todo en orden estable y respeta la categoría', () => {
  const idx = crearIndice(catalogo)
  assert.equal(buscar(idx, '').length, 6)
  assert.deepEqual(nombres(buscar(idx, '', { categoria: 'Panes' })), ['Pan francés', 'Pan lactal'])
  assert.deepEqual(nombres(buscar(idx, 'le', { categoria: 'Panes' })), [])
})

test('el orden no depende del stock: un refresco del stock no reordena la lista', () => {
  const antes = nombres(buscar(crearIndice(catalogo), 'medialuna'))
  const otroStock = catalogo.map((p) => ({ ...p, stock_disponible: (p.id * 37) % 11 }))
  assert.deepEqual(nombres(buscar(crearIndice(otroStock), 'medialuna')), antes)
  assert.deepEqual(nombres(buscar(crearIndice([...catalogo].reverse()), 'medialuna')), antes)
})

test('parsearConsulta separa el multiplicador', () => {
  assert.deepEqual(parsearConsulta('12*med'), { multiplicador: 12, texto: 'med' })
  assert.deepEqual(parsearConsulta('12x med'), { multiplicador: 12, texto: 'med' })
  assert.deepEqual(parsearConsulta(' 3 × pan '), { multiplicador: 3, texto: 'pan' })
  assert.deepEqual(parsearConsulta('12*'), { multiplicador: 12, texto: '' })
  assert.deepEqual(parsearConsulta('med'), { multiplicador: null, texto: 'med' })
  assert.deepEqual(parsearConsulta('202'), { multiplicador: null, texto: '202' })
  assert.deepEqual(parsearConsulta('0*med'), { multiplicador: null, texto: 'med' })
  assert.deepEqual(parsearConsulta(undefined), { multiplicador: null, texto: '' })
})
