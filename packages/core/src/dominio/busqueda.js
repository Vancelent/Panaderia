// Búsqueda de productos en memoria: sin pedidos al servidor por tecla, sin acentos, con código exacto
// primero. El orden depende solo de la consulta (nunca del stock), así el refresco periódico del stock no
// reordena la lista ni mueve la selección.

export const normalizar = (s) =>
  String(s ?? '')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .trim()

const palabras = (s) => s.split(/[^a-z0-9]+/).filter(Boolean)

/** Índice a partir del catálogo (los productos que ya trae TanStack Query). */
export function crearIndice(productos) {
  const items = productos.map((producto) => {
    const nombre = normalizar(producto.nombre)
    return {
      producto,
      nombre,
      codigo: normalizar(producto.codigo),
      palabras: palabras(nombre),
      categoria: normalizar(producto.categoria),
    }
  })
  // Orden base estable: por código (numérico si lo es) y luego por nombre
  items.sort(
    (a, b) =>
      a.nombre.localeCompare(b.nombre, 'es') || a.producto.id - b.producto.id,
  )
  return { items }
}

/** "12*med" o "12x med" → { multiplicador: 12, texto: 'med' }. Sin prefijo, multiplicador es null. */
export function parsearConsulta(consulta) {
  const m = /^\s*(\d{1,4})\s*[*x×]\s*(.*)$/i.exec(consulta ?? '')
  if (!m) return { multiplicador: null, texto: String(consulta ?? '').trim() }
  const n = Number(m[1])
  return { multiplicador: n > 0 ? n : null, texto: m[2].trim() }
}

function puntaje(item, tokens) {
  let total = 0
  for (const t of tokens) {
    let p = 0
    if (item.codigo && item.codigo === t) p = 1000
    else if (item.nombre.startsWith(t)) p = 500
    else if (item.codigo && item.codigo.startsWith(t)) p = 400
    else if (item.palabras.some((w) => w.startsWith(t))) p = 300
    else if (item.nombre.includes(t)) p = 100
    if (p === 0) return 0 // todas las palabras tienen que coincidir
    total += p
  }
  return total
}

/** Productos que coinciden, por relevancia y, en empate, por nombre (estable). */
export function buscar(indice, texto, { categoria = null } = {}) {
  const q = normalizar(texto)
  const catNorm = categoria ? normalizar(categoria) : null
  const candidatos = indice.items.filter((i) => !catNorm || i.categoria === catNorm)
  if (!q) return candidatos.map((i) => i.producto)
  const tokens = q.split(/\s+/)
  return candidatos
    .map((item) => ({ item, p: puntaje(item, tokens) }))
    .filter((x) => x.p > 0)
    .sort((a, b) => b.p - a.p) // Array.sort es estable: en empate queda el orden base
    .map((x) => x.item.producto)
}

/** Producto cuyo código es exactamente `texto` (lector de códigos de barras o tipeo directo). */
export function porCodigo(indice, texto) {
  const q = normalizar(texto)
  if (!q) return null
  return indice.items.find((i) => i.codigo === q)?.producto ?? null
}
