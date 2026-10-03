// Controlador de caja: lógica pura, sin UI (ni React DOM ni React Native). Es un reducer
// (estado + acción → estado) compartido por la vista de teclado, la táctil y la caja de la app.
//
// Maneja el catálogo con su índice de búsqueda, el buscador (con multiplicador "12*med"), la selección de
// resultados y el ticket. Los importes se calculan en centavos enteros y son solo para mostrar: el total
// que se cobra lo calcula el servidor.

import { buscar, crearIndice, parsearConsulta, porCodigo } from './busqueda.js'

export const MULTIPLICADORES = [
  { n: 1, label: '×1' },
  { n: 2, label: '×2' },
  { n: 6, label: '½ doc' },
  { n: 12, label: 'Doc' },
]

export function estadoInicial() {
  return {
    catalogo: [],
    porId: {},
    indice: crearIndice([]),
    consulta: '',
    seleccion: 0, // posición resaltada en los resultados
    categoria: null,
    multiplicador: 1, // el de los botones táctiles (×2, ½ doc…); el de la consulta ("12*") tiene prioridad
    lineas: [], // [{ productoId, cantidad }] en el orden en que se agregaron
    lineaSel: 0, // posición resaltada en el ticket
    aviso: null, // último hecho a anunciar: { tipo, producto?, cantidad? }
  }
}

const centavos = (v) => Math.round((Number(v) || 0) * 100)
const limitar = (n, min, max) => Math.max(min, Math.min(max, n))

// ---------- Selectores ----------

export const resultados = (e) => buscar(e.indice, parsearConsulta(e.consulta).texto, { categoria: e.categoria })

export const categorias = (e) =>
  [...new Set(e.catalogo.map((p) => p.categoria).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'es'))

/** Cantidad con la que se agrega el próximo producto: la del "12*" tipeado o la de los botones. */
export const multiplicadorActivo = (e) => parsearConsulta(e.consulta).multiplicador ?? e.multiplicador

export const lineasDetalladas = (e) =>
  e.lineas
    .map((l) => {
      const producto = e.porId[l.productoId]
      if (!producto) return null
      return {
        producto,
        cantidad: l.cantidad,
        subtotalCentavos: centavos(producto.precio_venta) * l.cantidad,
        // El stock pudo bajar en otra caja después de agregarlo: se avisa, y el servidor decide al cobrar
        excede: l.cantidad > producto.stock_disponible,
      }
    })
    .filter(Boolean)

export const totalCentavos = (e) => lineasDetalladas(e).reduce((t, l) => t + l.subtotalCentavos, 0)
export const unidades = (e) => lineasDetalladas(e).reduce((t, l) => t + l.cantidad, 0)
export const cantidadEnTicket = (e, productoId) => e.lineas.find((l) => l.productoId === productoId)?.cantidad ?? 0
export const disponibleParaAgregar = (e, producto) =>
  Math.max(0, producto.stock_disponible - cantidadEnTicket(e, producto.id))

/** Para el servidor: solo producto y cantidad; precios y total los calcula él. */
export const itemsParaVenta = (e) =>
  lineasDetalladas(e).map((l) => ({ producto_id: l.producto.id, cantidad: l.cantidad }))

// ---------- Reducer ----------

function agregarProducto(e, producto, pedida) {
  const enTicket = cantidadEnTicket(e, producto.id)
  const cantidad = Math.min(pedida, producto.stock_disponible - enTicket)
  if (cantidad <= 0) {
    return { ...e, consulta: '', seleccion: 0, aviso: { tipo: 'sin_stock', producto, cantidad: 0 } }
  }
  const existe = e.lineas.some((l) => l.productoId === producto.id)
  const lineas = existe
    ? e.lineas.map((l) => (l.productoId === producto.id ? { ...l, cantidad: l.cantidad + cantidad } : l))
    : [...e.lineas, { productoId: producto.id, cantidad }]
  return {
    ...e,
    lineas,
    lineaSel: lineas.findIndex((l) => l.productoId === producto.id),
    // Después de agregar, el buscador y el multiplicador vuelven a cero (el foco vuelve al buscador)
    consulta: '',
    seleccion: 0,
    multiplicador: 1,
    aviso: { tipo: cantidad < pedida ? 'tope' : 'agregado', producto, cantidad },
  }
}

function conLineas(e, lineas) {
  return { ...e, lineas, lineaSel: limitar(e.lineaSel, 0, Math.max(0, lineas.length - 1)), aviso: null }
}

export function reducir(e, accion) {
  switch (accion.tipo) {
    case 'catalogo': {
      const catalogo = accion.productos.filter((p) => p.activo !== false)
      const nuevo = {
        ...e,
        catalogo,
        porId: Object.fromEntries(catalogo.map((p) => [p.id, p])),
        indice: crearIndice(catalogo),
      }
      // Lo que ya está en el ticket sigue ahí; la selección se acota al largo de los resultados nuevos
      return { ...nuevo, seleccion: limitar(e.seleccion, 0, Math.max(0, resultados(nuevo).length - 1)) }
    }
    case 'escribir':
      return { ...e, consulta: accion.texto, seleccion: 0, aviso: null }
    case 'limpiar_busqueda':
      return {
        ...e,
        consulta: '',
        seleccion: 0,
        multiplicador: 1,
        categoria: accion.conservarCategoria ? e.categoria : null,
      }
    case 'mover': {
      const n = resultados(e).length
      return { ...e, seleccion: n ? limitar(e.seleccion + accion.delta, 0, n - 1) : 0 }
    }
    case 'categoria':
      return { ...e, categoria: accion.categoria, seleccion: 0 }
    case 'fijar_multiplicador':
      return { ...e, multiplicador: accion.n }
    case 'agregar': {
      // Con un toque o un clic: un producto concreto, con la cantidad de los botones táctiles
      const producto = e.porId[accion.productoId]
      if (!producto) return e
      return agregarProducto(e, producto, accion.cantidad ?? multiplicadorActivo(e))
    }
    case 'enter': {
      // Enter en el buscador: código exacto primero (un lector de códigos escribe como un teclado),
      // si no, el resultado resaltado
      const { texto } = parsearConsulta(e.consulta)
      const producto = porCodigo(e.indice, texto) ?? resultados(e)[e.seleccion]
      if (!producto) return { ...e, aviso: { tipo: 'sin_resultados', texto } }
      return agregarProducto(e, producto, multiplicadorActivo(e))
    }
    case 'ticket_mover':
      return {
        ...e,
        lineaSel: e.lineas.length ? limitar(e.lineaSel + accion.delta, 0, e.lineas.length - 1) : 0,
      }
    case 'ticket_sumar':
    case 'ticket_restar': {
      const linea = e.lineas[e.lineaSel]
      if (!linea) return e
      const producto = e.porId[linea.productoId]
      const cantidad = linea.cantidad + (accion.tipo === 'ticket_sumar' ? 1 : -1)
      if (cantidad <= 0) return reducir(e, { tipo: 'ticket_quitar' })
      if (producto && cantidad > producto.stock_disponible) {
        return { ...e, aviso: { tipo: 'tope', producto, cantidad: 0 } }
      }
      return conLineas(e, e.lineas.map((l) => (l === linea ? { ...l, cantidad } : l)))
    }
    case 'ticket_quitar': {
      const linea = e.lineas[e.lineaSel]
      if (!linea) return e
      const producto = e.porId[linea.productoId]
      const nuevo = conLineas(e, e.lineas.filter((l) => l !== linea))
      return { ...nuevo, aviso: { tipo: 'quitado', producto, cantidad: linea.cantidad } }
    }
    case 'fijar_cantidad': {
      // Desde el selector de cantidad del ticket (táctil). 0 quita la línea; no pasa del stock disponible
      const producto = e.porId[accion.productoId]
      const tope = producto ? producto.stock_disponible : Number(accion.cantidad) || 0
      const cantidad = limitar(Math.floor(Number(accion.cantidad) || 0), 0, tope)
      return conLineas(
        e,
        cantidad > 0
          ? e.lineas.map((l) => (l.productoId === accion.productoId ? { ...l, cantidad } : l))
          : e.lineas.filter((l) => l.productoId !== accion.productoId),
      )
    }
    case 'vaciar':
      return { ...e, lineas: [], lineaSel: 0, aviso: null }
    case 'vendido':
      return { ...e, lineas: [], lineaSel: 0, consulta: '', seleccion: 0, multiplicador: 1, aviso: null }
    default:
      return e
  }
}

/** Texto para anunciar en una región `aria-live` (lectores de pantalla). */
export function anuncio(e) {
  const a = e.aviso
  if (!a) return ''
  const nombre = a.producto?.nombre ?? ''
  switch (a.tipo) {
    case 'agregado':
      return `Agregado: ${a.cantidad} ${nombre}`
    case 'tope':
      return a.cantidad > 0
        ? `Solo se agregaron ${a.cantidad} de ${nombre}: no hay más disponible`
        : `No hay más ${nombre} disponible`
    case 'sin_stock':
      return `No hay más ${nombre} disponible`
    case 'quitado':
      return `Quitado: ${nombre}`
    case 'sin_resultados':
      return `Sin resultados para ${a.texto}`
    default:
      return ''
  }
}
