import { useQuery } from '@tanstack/react-query'
import { get } from './api'

// Claves de caché centralizadas: invalidar ['productos'] refresca todas sus variantes.
export const qk = {
  me: ['me'],
  productos: (params) => ['productos', params ?? {}],
  materiasPrimas: ['materias-primas'],
  receta: (id) => ['receta', id],
  turnoActual: ['turno-actual'],
  ventasTurno: ['ventas-turno'],
  turnosAbiertos: ['turnos-abiertos'],
  pedidos: (params) => ['pedidos', params ?? {}],
  pendienteProduccion: ['pendiente-produccion'],
  clientes: (buscar) => ['clientes', buscar ?? ''],
  resumen: (desde, hasta) => ['resumen', desde, hasta],
  alertas: ['alertas'],
  arqueos: ['arqueos'],
  usuarios: ['usuarios'],
  proveedores: ['proveedores'],
  compras: ['compras'],
  gastos: ['gastos'],
}

export const useProductos = (params) =>
  useQuery({ queryKey: qk.productos(params), queryFn: () => get('/productos', params) })

export const useMateriasPrimas = () =>
  useQuery({ queryKey: qk.materiasPrimas, queryFn: () => get('/materias-primas') })

export const useReceta = (productoId) =>
  useQuery({
    queryKey: qk.receta(productoId),
    queryFn: () => get(`/productos/${productoId}/receta`),
    enabled: !!productoId,
  })

export const useTurnoActual = () =>
  useQuery({ queryKey: qk.turnoActual, queryFn: () => get('/turnos/actual') })

export const useVentasTurno = (enabled = true) =>
  useQuery({ queryKey: qk.ventasTurno, queryFn: () => get('/turnos/actual/ventas'), enabled })

export const useTurnosAbiertos = () =>
  useQuery({ queryKey: qk.turnosAbiertos, queryFn: () => get('/turnos/abiertos') })

export const usePedidos = (params) =>
  useQuery({
    queryKey: qk.pedidos(params),
    queryFn: () => get('/pedidos', params),
    refetchInterval: 30_000, // el tablero de comandas se mantiene al día solo
  })

export const usePendienteProduccion = () =>
  useQuery({
    queryKey: qk.pendienteProduccion,
    queryFn: () => get('/produccion/pendiente'),
    refetchInterval: 60_000,
  })

export const useClientes = (buscar) =>
  useQuery({
    queryKey: qk.clientes(buscar),
    queryFn: () => get('/clientes', buscar ? { buscar } : undefined),
    placeholderData: (prev) => prev,
  })

export const useResumen = (desde, hasta) =>
  useQuery({
    queryKey: qk.resumen(desde, hasta),
    queryFn: () => get('/finanzas/resumen', { desde, hasta }),
    placeholderData: (prev) => prev,
  })

export const useAlertas = () => useQuery({ queryKey: qk.alertas, queryFn: () => get('/stock/alertas') })
export const useArqueos = () => useQuery({ queryKey: qk.arqueos, queryFn: () => get('/arqueos') })
export const useUsuarios = () => useQuery({ queryKey: qk.usuarios, queryFn: () => get('/usuarios') })
export const useProveedores = () =>
  useQuery({ queryKey: qk.proveedores, queryFn: () => get('/proveedores') })
export const useCompras = () => useQuery({ queryKey: qk.compras, queryFn: () => get('/compras') })
export const useGastos = () => useQuery({ queryKey: qk.gastos, queryFn: () => get('/gastos') })
