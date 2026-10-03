import { useEffect, useMemo, useReducer } from 'react'
import { caja } from '@panaderia/core'
import { useToast } from '../../components/ui/toast'
import { useProductos } from '../../lib/queries'

const AVISOS_VISIBLES = ['tope', 'sin_stock', 'sin_resultados']

/**
 * Adaptador React del controlador de caja compartido (packages/core). Mantiene el estado con un reducer
 * puro y le pasa el catálogo que ya trae TanStack Query (con su refresco de 8 s). Las dos vistas, la de
 * teclado y la táctil, usan este mismo hook: cambiar de dispositivo es cambiar la vista, no la lógica.
 */
export function usePos() {
  const productosQ = useProductos()
  const toast = useToast()
  const [estado, despachar] = useReducer(caja.reducir, undefined, caja.estadoInicial)

  // El catálogo se actualiza solo: el ticket y la selección no se mueven
  useEffect(() => {
    if (productosQ.data) despachar({ tipo: 'catalogo', productos: productosQ.data })
  }, [productosQ.data])

  const { indice, consulta, categoria, lineas, porId, aviso } = estado
  const resultados = useMemo(() => caja.resultados({ indice, consulta, categoria }), [indice, consulta, categoria])
  const detalle = useMemo(() => caja.lineasDetalladas({ lineas, porId }), [lineas, porId])
  const categorias = useMemo(() => caja.categorias({ catalogo: estado.catalogo }), [estado.catalogo])
  const anuncio = useMemo(() => caja.anuncio({ aviso }), [aviso])

  // Lo que no se pudo hacer (sin stock, sin resultados) también se ve, no solo se anuncia
  useEffect(() => {
    if (aviso && AVISOS_VISIBLES.includes(aviso.tipo)) toast.info(caja.anuncio({ aviso }))
  }, [aviso, toast])

  return {
    estado,
    despachar,
    productosQ,
    resultados,
    categorias,
    lineas: detalle,
    anuncio,
    totalCentavos: detalle.reduce((t, l) => t + l.subtotalCentavos, 0),
    unidades: detalle.reduce((t, l) => t + l.cantidad, 0),
    items: useMemo(() => detalle.map((l) => ({ producto_id: l.producto.id, cantidad: l.cantidad })), [detalle]),
  }
}
