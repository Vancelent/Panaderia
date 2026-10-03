import assert from 'node:assert/strict'
import { test } from 'node:test'
import { ROL, inicioPorRol, navPara } from '../src/roles.js'
import { nivelStock } from '../src/dominio/stock.js'
import { fmtDinero, isoLocal, sumarDias } from '../src/formato.js'
import { qk } from '../src/consultas.js'
import {
  CODIGO_REAUTENTICACION,
  estrategiaBearer,
  estrategiaCookies,
  instalarSesion,
  mensajeError,
} from '../src/api/sesion.js'

// Un "axios" mínimo: guarda los interceptores y permite simular respuestas
function apiFalsa(respuestas) {
  const api = { interceptors: { request: [], response: [] }, enviadas: [] }
  api.interceptors.request.use = (f) => api.interceptors.request.push(f)
  api.interceptors.response.use = (ok, err) => api.interceptors.response.push({ ok, err })
  api.request = async (config) => {
    const cfg = { ...config, headers: { ...config.headers } }
    for (const f of api.interceptors.request) await f(cfg)
    api.enviadas.push(cfg)
    const r = respuestas.shift()
    if (r.error) {
      // Como axios: el manejador puede devolver una respuesta (p. ej. tras reintentar) o volver a lanzar
      const error = { config: cfg, response: r.error }
      for (const h of api.interceptors.response) return await h.err(error)
    }
    return r
  }
  return api
}

test('estrategia de cookies: el CSRF viaja solo en escrituras y con o sin el prefijo __Host-', () => {
  const cookies = { '__Host-panaderia_csrf': 'abc' }
  const e = estrategiaCookies({ leerCookie: (n) => cookies[n] ?? null })
  const post = { method: 'post', headers: {} }
  e.preparar(post)
  assert.equal(post.headers['X-CSRF-Token'], 'abc')
  const get = { method: 'get', headers: {} }
  e.preparar(get)
  assert.equal(get.headers['X-CSRF-Token'], undefined)
  const sinPrefijo = estrategiaCookies({ leerCookie: (n) => ({ panaderia_csrf: 'xyz' })[n] ?? null })
  const put = { method: 'put', headers: {} }
  sinPrefijo.preparar(put)
  assert.equal(put.headers['X-CSRF-Token'], 'xyz')
})

test('estrategia Bearer: agrega el access token', async () => {
  const e = estrategiaBearer({ obtenerAccess: async () => 'tok' })
  const cfg = { headers: {} }
  await e.preparar(cfg)
  assert.equal(cfg.headers.Authorization, 'Bearer tok')
  const sin = { headers: {} }
  await estrategiaBearer({ obtenerAccess: async () => null }).preparar(sin)
  assert.equal(sin.headers.Authorization, undefined)
})

test('un 401 de reautenticación pide confirmar y repite la solicitud original una vez', async () => {
  const reauth = { error: { status: 401, data: { error: { code: CODIGO_REAUTENTICACION } } } }
  const api = apiFalsa([reauth, { data: 'ok' }])
  let pedidas = 0
  instalarSesion(api, estrategiaCookies({ leerCookie: () => 'csrf' }), {
    pedirReautenticacion: async () => { pedidas += 1 },
    alSesionExpirada: () => assert.fail('no es una sesión vencida'),
  })
  const r = await api.request({ method: 'post', url: '/productos', headers: {} })
  assert.equal(r.data, 'ok')
  assert.equal(pedidas, 1)
  assert.equal(api.enviadas.length, 2)
  assert.equal(api.enviadas[1].__reintentada, true)
})

test('si la persona cancela la reautenticación, el error original se propaga', async () => {
  const reauth = { error: { status: 401, data: { error: { code: CODIGO_REAUTENTICACION } } } }
  const api = apiFalsa([reauth])
  instalarSesion(api, estrategiaCookies({ leerCookie: () => null }), {
    pedirReautenticacion: async () => { throw new Error('cancelada') },
  })
  await assert.rejects(api.request({ method: 'post', url: '/x', headers: {} }), /cancelada/)
})

test('no se pide la reautenticación dos veces para la misma solicitud', async () => {
  const reauth = { error: { status: 401, data: { error: { code: CODIGO_REAUTENTICACION } } } }
  const api = apiFalsa([reauth, reauth])
  let pedidas = 0
  instalarSesion(api, estrategiaCookies({ leerCookie: () => null }), {
    pedirReautenticacion: async () => { pedidas += 1 },
  })
  await assert.rejects(api.request({ method: 'post', url: '/x', headers: {} }))
  assert.equal(pedidas, 1)
})

test('cualquier otro 401 fuera de /auth/ avisa que la sesión venció', async () => {
  let vencida = 0
  const api = apiFalsa([{ error: { status: 401, data: { error: { code: 'unauthorized' } } } },
    { error: { status: 401, data: { error: { code: 'invalid_credentials' } } } }])
  instalarSesion(api, estrategiaCookies({ leerCookie: () => null }), { alSesionExpirada: () => { vencida += 1 } })
  await assert.rejects(api.request({ method: 'get', url: '/productos', headers: {} }))
  assert.equal(vencida, 1)
  await assert.rejects(api.request({ method: 'post', url: '/auth/login', headers: {} }))
  assert.equal(vencida, 1) // un login fallido no cierra la sesión
})

test('mensajeError', () => {
  assert.equal(mensajeError(null), 'Ocurrió un error. Intentá de nuevo.')
  assert.equal(mensajeError({ code: 'ECONNABORTED' }), 'El servidor tardó demasiado en responder.')
  assert.equal(mensajeError({}), 'Sin conexión con el servidor.')
  assert.equal(mensajeError({ response: { data: { error: { message: 'Stock insuficiente' } } } }), 'Stock insuficiente')
  assert.equal(mensajeError({ response: { data: { error: { code: 'validation_error', details: [{ campo: 'pin', mensaje: 'inválido' }, { mensaje: 'x' }] } } } }), 'pin: inválido · x')
})

test('roles: inicio y navegación por rol', () => {
  assert.equal(inicioPorRol(ROL.ADMIN), '/admin')
  assert.equal(inicioPorRol(ROL.ENCARGADA), '/admin')
  assert.equal(inicioPorRol(ROL.VENDEDORA), '/caja')
  assert.equal(inicioPorRol(ROL.PANADERO), '/produccion')
  assert.equal(inicioPorRol(ROL.REPARTIDOR), '/reparto')
  assert.equal(inicioPorRol('Otro'), '/login')
  assert.deepEqual(navPara(ROL.REPARTIDOR).map((n) => n.to), ['/reparto'])
  assert.equal(navPara(ROL.VENDEDORA).some((n) => n.to === '/admin/usuarios'), false)
  assert.equal(navPara(ROL.ADMIN).some((n) => n.to === '/admin/usuarios'), true)
  assert.equal(navPara(ROL.PANADERO).some((n) => n.to === '/pedidos'), true)
  assert.equal(navPara(ROL.REPARTIDOR).some((n) => n.to === '/stock'), false)
})

test('nivel de stock y formato', () => {
  assert.equal(nivelStock(0, 5).tone, 'red')
  assert.equal(nivelStock(5, 5).label, 'Bajo mínimo')
  assert.equal(nivelStock(7, 5).tone, 'amber')
  assert.equal(nivelStock(50, 5).tone, 'green')
  assert.match(fmtDinero(1234.5), /1\.234,50/)
  assert.equal(isoLocal(new Date(2026, 9, 2)), '2026-10-02')
  assert.equal(isoLocal(sumarDias(new Date(2026, 9, 30), 3)), '2026-11-02')
  assert.deepEqual(qk.productos(), ['productos', {}])
})
